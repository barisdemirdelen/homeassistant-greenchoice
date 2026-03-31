from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.const import CONF_NAME
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.greenchoice.api import GreenchoiceApi
from custom_components.greenchoice.const import DOMAIN
from custom_components.greenchoice.hourly_statistics import (
    _get_days_with_data,
    async_import_yesterday_hourly_statistics,
    hourly_consumption_entity_id,
)


def _entry(hass, entry_id):
    """Create and register a MockConfigEntry with standard test values."""
    e = MockConfigEntry(
        domain=DOMAIN,
        entry_id=entry_id,
        title="Greenchoice (Test)",
        data={CONF_NAME: "My Home"},
    )
    e.add_to_hass(hass)
    return e


def _make_consumptions_payload(
    date_str: str, total_delivery: float, total_feed_in: float = 0.0
) -> dict:
    """Build a single-point hourly consumptions API response for the given date."""
    end_str = (date.fromisoformat(date_str) + timedelta(days=1)).isoformat()
    return {
        "interval": "Hour",
        "start": f"{date_str}T00:00:00",
        "end": f"{end_str}T00:00:00",
        "consumptionCosts": [
            {
                "consumedOn": f"{date_str}T00:00:00",
                "electricity": {
                    "totalDeliveryConsumption": total_delivery,
                    "totalFeedInConsumption": total_feed_in,
                    "hasConsumption": True,
                },
                "hasConsumption": True,
            }
        ],
    }


@pytest.mark.asyncio
async def test_import_yesterday_hourly_statistics_imports_and_is_idempotent(
    hass,
    mock_api,
    consumptions_hour_response,
    mock_import_statistics,
    patch_hourly_now,
    patch_recorder_days,
):
    dt_util.set_default_time_zone(timezone.utc)
    hass.config.components.add("recorder")
    entry = _entry(hass, "abc123")

    fixed_now_early = datetime(2026, 3, 28, 4, 0, tzinfo=UTC)
    fixed_now_later = datetime(2026, 3, 28, 16, 0, tzinfo=UTC)
    all_days_except_yesterday = {
        date(2026, 3, 21) + timedelta(days=i): 1.0 for i in range(6)
    }
    all_days_present = {date(2026, 3, 21) + timedelta(days=i): 1.0 for i in range(7)}

    mock_api(consumptions={"2026-03-27": consumptions_hour_response})

    async with GreenchoiceApi("fake_user", "fake_password") as api:
        # 1. Before 13:00 with only yesterday missing → deferred, return None.
        with (
            patch_hourly_now(fixed_now_early),
            patch_recorder_days(all_days_except_yesterday),
        ):
            res_early = await async_import_yesterday_hourly_statistics(
                hass, api=api, entry=entry
            )
        assert res_early is None
        assert mock_import_statistics.call_count == 0

        # 2. After 13:00 → imports March 27 (24 points).
        mock_import_statistics.reset_mock()
        with patch_hourly_now(fixed_now_later), patch_recorder_days({}):
            res = await async_import_yesterday_hourly_statistics(
                hass, api=api, entry=entry
            )
        assert res is not None
        assert res.imported is True
        assert res.date.isoformat() == "2026-03-27"
        assert res.points == 24
        assert mock_import_statistics.call_count == 2  # consumption + feed-in

        consumption_meta = mock_import_statistics.call_args_list[0].args[1]
        feed_in_meta = mock_import_statistics.call_args_list[1].args[1]

        def _stat_id(m):
            return m["statistic_id"] if isinstance(m, dict) else m.statistic_id

        def _source(m):
            return m["source"] if isinstance(m, dict) else m.source

        assert (
            _stat_id(consumption_meta)
            == "sensor.my_home_electricity_consumption_hourly"
        )
        assert _source(consumption_meta) == "recorder"
        assert _stat_id(feed_in_meta) == "sensor.my_home_electricity_feed_in_hourly"
        assert _source(feed_in_meta) == "recorder"

        def _sum(s):
            return s["sum"] if isinstance(s, dict) else s.sum

        consumption_stats = mock_import_statistics.call_args_list[0].args[2]
        assert float(_sum(consumption_stats[0])) == pytest.approx(0.458)
        assert float(_sum(consumption_stats[1])) == pytest.approx(0.530)

        feed_in_stats = mock_import_statistics.call_args_list[1].args[2]
        assert float(_sum(feed_in_stats[0])) == pytest.approx(0.0)
        assert float(_sum(feed_in_stats[1])) == pytest.approx(0.0)

        # 3. All days present → no import (idempotent).
        mock_import_statistics.reset_mock()
        with patch_hourly_now(fixed_now_later), patch_recorder_days(all_days_present):
            res2 = await async_import_yesterday_hourly_statistics(
                hass, api=api, entry=entry
            )
        assert res2 is not None
        assert res2.imported is False
        assert mock_import_statistics.call_count == 0


@pytest.mark.asyncio
async def test_import_before_13_still_backfills_older_gaps(
    hass,
    mock_api,
    mock_import_statistics,
    patch_hourly_now,
    patch_recorder_days,
):
    """Before 13:00, yesterday is deferred but older missing days are still imported."""
    dt_util.set_default_time_zone(timezone.utc)
    hass.config.components.add("recorder")
    entry = _entry(hass, "abc123_early")

    recorder_has_data = {
        date(2026, 3, 21) + timedelta(days=i): float(i + 1) for i in range(5)
    }
    context = mock_api(
        consumptions={"2026-03-26": _make_consumptions_payload("2026-03-26", 5.0)}
    )

    with (
        patch_hourly_now(datetime(2026, 3, 28, 10, 0, tzinfo=UTC)),
        patch_recorder_days(recorder_has_data),
    ):
        async with GreenchoiceApi("fake_user", "fake_password") as api:
            res = await async_import_yesterday_hourly_statistics(
                hass, api=api, entry=entry
            )

    assert res is not None
    assert res.imported is True
    assert res.date == date(2026, 3, 26)
    assert res.points == 1
    assert (
        mock_import_statistics.call_count == 2
    )  # consumption + feed-in for March 26 only
    # March 27 (yesterday) must NOT have been fetched — deferred until after 13:00.
    assert not any("start=2026-03-27" in str(url) for (_, url) in context.requests)


@pytest.mark.asyncio
async def test_import_yesterday_hourly_statistics_backfills_gap(
    hass,
    mock_api,
    mock_import_statistics,
    patch_hourly_now,
    patch_recorder_days,
):
    """Two missing days are imported with correctly chained cumulative sums."""
    dt_util.set_default_time_zone(timezone.utc)
    hass.config.components.add("recorder")
    entry = _entry(hass, "abc123_gap")

    recorder_has_data = {
        date(2026, 3, 21): 40.0,
        date(2026, 3, 22): 55.0,
        date(2026, 3, 23): 68.0,
        date(2026, 3, 24): 82.0,
        date(2026, 3, 25): 100.0,
    }
    day_26_consumption, day_27_consumption = 10.0, 6.0
    mock_api(
        consumptions={
            "2026-03-26": _make_consumptions_payload("2026-03-26", day_26_consumption),
            "2026-03-27": _make_consumptions_payload("2026-03-27", day_27_consumption),
        }
    )

    with (
        patch_hourly_now(datetime(2026, 3, 28, 16, 0, tzinfo=UTC)),
        patch_recorder_days(dict(recorder_has_data), {}),
    ):
        async with GreenchoiceApi("fake_user", "fake_password") as api:
            res = await async_import_yesterday_hourly_statistics(
                hass, api=api, entry=entry
            )

    assert res.imported is True
    assert res.date == date(2026, 3, 27)
    assert res.points == 2
    assert mock_import_statistics.call_count == 4  # consumption + feed-in, twice

    def _sum(s):
        return s["sum"] if isinstance(s, dict) else s.sum

    assert float(
        _sum(mock_import_statistics.call_args_list[0].args[2][0])
    ) == pytest.approx(100.0 + day_26_consumption)
    assert float(
        _sum(mock_import_statistics.call_args_list[2].args[2][0])
    ) == pytest.approx(100.0 + day_26_consumption + day_27_consumption)


@pytest.mark.asyncio
async def test_import_corrects_stale_sums_after_gap(
    hass,
    mock_api,
    mock_import_statistics,
    patch_hourly_now,
    patch_recorder_days,
):
    """Days after a gap are re-imported to correct their stale cumulative sums."""
    dt_util.set_default_time_zone(timezone.utc)
    hass.config.components.add("recorder")
    entry = _entry(hass, "abc123_stale")

    day_26_consumption, day_27_consumption = 10.0, 6.0
    stale_sum_march_27 = (
        100.0 + day_27_consumption
    )  # wrong: built on March 25, skipping 26

    recorder_consumption = {
        date(2026, 3, 21): 40.0,
        date(2026, 3, 22): 55.0,
        date(2026, 3, 23): 68.0,
        date(2026, 3, 24): 82.0,
        date(2026, 3, 25): 100.0,
        date(2026, 3, 27): stale_sum_march_27,  # March 26 absent (gap)
    }
    mock_api(
        consumptions={
            "2026-03-26": _make_consumptions_payload("2026-03-26", day_26_consumption),
            "2026-03-27": _make_consumptions_payload("2026-03-27", day_27_consumption),
        }
    )

    with (
        patch_hourly_now(datetime(2026, 3, 28, 16, 0, tzinfo=UTC)),
        patch_recorder_days(dict(recorder_consumption), {}),
    ):
        async with GreenchoiceApi("fake_user", "fake_password") as api:
            res = await async_import_yesterday_hourly_statistics(
                hass, api=api, entry=entry
            )

    assert res.imported is True
    assert res.points == 2
    assert mock_import_statistics.call_count == 4

    def _sum(s):
        return s["sum"] if isinstance(s, dict) else s.sum

    assert float(
        _sum(mock_import_statistics.call_args_list[0].args[2][0])
    ) == pytest.approx(100.0 + day_26_consumption)
    correct_sum = 100.0 + day_26_consumption + day_27_consumption
    assert float(
        _sum(mock_import_statistics.call_args_list[2].args[2][0])
    ) == pytest.approx(correct_sum)
    assert float(
        _sum(mock_import_statistics.call_args_list[2].args[2][0])
    ) != pytest.approx(stale_sum_march_27)


@pytest.mark.asyncio
async def test_import_yesterday_hourly_statistics_retries_on_empty(
    hass,
    mock_api,
    patch_hourly_now,
    patch_recorder_days,
):
    """If the API returns no data, last sums are NOT saved so the next cycle retries."""
    dt_util.set_default_time_zone(timezone.utc)
    hass.config.components.add("recorder")
    entry = _entry(hass, "abc123_empty")

    mock_api(consumptions={})  # all dates return empty automatically

    with (
        patch_hourly_now(datetime(2026, 3, 28, 15, 0, tzinfo=UTC)),
        patch_recorder_days({}),
        patch("homeassistant.helpers.storage.Store.async_save") as mock_save,
    ):
        async with GreenchoiceApi("fake_user", "fake_password") as api:
            res = await async_import_yesterday_hourly_statistics(
                hass, api=api, entry=entry
            )

    assert res is not None
    assert res.imported is False
    assert res.points == 0
    mock_save.assert_not_called()


@pytest.mark.asyncio
async def test_get_days_with_data_handles_float_timestamps(hass):
    """Recorder in newer HA versions returns start as a Unix timestamp (float).
    _get_days_with_data must convert it to a datetime before calling dt_util.as_local,
    otherwise a 'float object has no attribute tzinfo' error is raised at runtime.
    """
    dt_util.set_default_time_zone(timezone.utc)
    hass.config.components.add("recorder")

    statistic_id = hourly_consumption_entity_id("My Home")
    target_date = date(2026, 3, 27)

    march_27_00_utc = datetime(2026, 3, 27, 0, 0, tzinfo=UTC)
    march_27_23_utc = datetime(2026, 3, 27, 23, 0, tzinfo=UTC)
    fake_stats = {
        statistic_id: [
            {"start": march_27_00_utc.timestamp(), "sum": 5.0},
            {"start": march_27_23_utc.timestamp(), "sum": 16.414},
        ]
    }

    with patch("homeassistant.components.recorder.get_instance") as mock_get_instance:
        mock_instance = Mock()
        mock_instance.async_add_executor_job = AsyncMock(return_value=fake_stats)
        mock_get_instance.return_value = mock_instance

        result = await _get_days_with_data(hass, statistic_id, target_date, target_date)

    assert target_date in result
    assert result[target_date] == pytest.approx(16.414)
