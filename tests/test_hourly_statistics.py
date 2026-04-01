from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.util import dt as dt_util

from custom_components.greenchoice.api import GreenchoiceApi
from custom_components.greenchoice.hourly_statistics import (
    _get_days_with_data,
    async_import_yesterday_hourly_statistics,
    async_reimport_hourly_statistics_from,
    hourly_consumption_entity_id,
)
from tests.conftest import make_consumptions_payload, stat_sum


@pytest.mark.asyncio
async def test_import_yesterday_hourly_statistics_imports_and_is_idempotent(
    hass,
    mock_api,
    consumptions_hour_response,
    mock_import_statistics,
    patch_hourly_now,
    patch_recorder_days,
    entry_factory,
):
    dt_util.set_default_time_zone(timezone.utc)
    hass.config.components.add("recorder")
    entry = entry_factory("abc123")

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

        consumption_stats = mock_import_statistics.call_args_list[0].args[2]
        assert stat_sum(consumption_stats[0]) == pytest.approx(0.458)
        assert stat_sum(consumption_stats[1]) == pytest.approx(0.530)

        feed_in_stats = mock_import_statistics.call_args_list[1].args[2]
        assert stat_sum(feed_in_stats[0]) == pytest.approx(0.0)
        assert stat_sum(feed_in_stats[1]) == pytest.approx(0.0)

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
    entry_factory,
):
    """Before 13:00, yesterday is deferred but older missing days are still imported."""
    dt_util.set_default_time_zone(timezone.utc)
    hass.config.components.add("recorder")
    entry = entry_factory("abc123_early")

    recorder_has_data = {
        date(2026, 3, 21) + timedelta(days=i): float(i + 1) for i in range(5)
    }
    context = mock_api(
        consumptions={"2026-03-26": make_consumptions_payload("2026-03-26", 5.0)}
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
    assert mock_import_statistics.call_count == 2
    # March 27 (yesterday) must NOT have been fetched — deferred until after 13:00.
    assert not any("start=2026-03-27" in str(url) for (_, url) in context.requests)


@pytest.mark.asyncio
async def test_import_yesterday_hourly_statistics_backfills_gap(
    hass,
    mock_api,
    mock_import_statistics,
    patch_hourly_now,
    patch_recorder_days,
    entry_factory,
):
    """Two missing days are imported with correctly chained cumulative sums."""
    dt_util.set_default_time_zone(timezone.utc)
    hass.config.components.add("recorder")
    entry = entry_factory("abc123_gap")

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
            "2026-03-26": make_consumptions_payload("2026-03-26", day_26_consumption),
            "2026-03-27": make_consumptions_payload("2026-03-27", day_27_consumption),
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

    assert stat_sum(
        mock_import_statistics.call_args_list[0].args[2][0]
    ) == pytest.approx(100.0 + day_26_consumption)
    assert stat_sum(
        mock_import_statistics.call_args_list[2].args[2][0]
    ) == pytest.approx(100.0 + day_26_consumption + day_27_consumption)


@pytest.mark.asyncio
async def test_import_corrects_stale_sums_after_gap(
    hass,
    mock_api,
    mock_import_statistics,
    patch_hourly_now,
    patch_recorder_days,
    entry_factory,
):
    """Days after a gap are re-imported to correct their stale cumulative sums."""
    dt_util.set_default_time_zone(timezone.utc)
    hass.config.components.add("recorder")
    entry = entry_factory("abc123_stale")

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
            "2026-03-26": make_consumptions_payload("2026-03-26", day_26_consumption),
            "2026-03-27": make_consumptions_payload("2026-03-27", day_27_consumption),
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

    assert stat_sum(
        mock_import_statistics.call_args_list[0].args[2][0]
    ) == pytest.approx(100.0 + day_26_consumption)
    correct_sum = 100.0 + day_26_consumption + day_27_consumption
    assert stat_sum(
        mock_import_statistics.call_args_list[2].args[2][0]
    ) == pytest.approx(correct_sum)
    assert stat_sum(
        mock_import_statistics.call_args_list[2].args[2][0]
    ) != pytest.approx(stale_sum_march_27)


@pytest.mark.asyncio
async def test_import_yesterday_hourly_statistics_retries_on_empty(
    hass,
    mock_api,
    patch_hourly_now,
    patch_recorder_days,
    entry_factory,
    patch_store_save,
):
    """If the API returns no data, last sums are NOT saved so the next cycle retries."""
    dt_util.set_default_time_zone(timezone.utc)
    hass.config.components.add("recorder")
    entry = entry_factory("abc123_empty")

    mock_api(consumptions={})  # all dates return empty automatically

    with (
        patch_hourly_now(datetime(2026, 3, 28, 15, 0, tzinfo=UTC)),
        patch_recorder_days({}),
    ):
        async with GreenchoiceApi("fake_user", "fake_password") as api:
            res = await async_import_yesterday_hourly_statistics(
                hass, api=api, entry=entry
            )

    assert res is not None
    assert res.imported is False
    assert res.points == 0
    patch_store_save.assert_not_called()


@pytest.mark.asyncio
async def test_get_days_with_data_handles_float_timestamps(hass):
    """Regression test: recorder returns start as a Unix timestamp (float) in newer HA.

    patch_recorder_days always supplies datetime objects, so this test is the only
    place that exercises the float-to-datetime conversion inside _get_days_with_data.
    Without it, a 'float object has no attribute tzinfo' error would go undetected.
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

    with patch(
        "custom_components.greenchoice.hourly_statistics.get_instance"
    ) as mock_get_instance:
        mock_instance = Mock()
        mock_instance.async_add_executor_job = AsyncMock(return_value=fake_stats)
        mock_get_instance.return_value = mock_instance

        result = await _get_days_with_data(hass, statistic_id, target_date, target_date)

    assert target_date in result
    assert result[target_date] == pytest.approx(16.414)


@pytest.mark.asyncio
async def test_import_yesterday_hourly_statistics_with_gas(
    hass,
    mock_api,
    consumptions_hour_with_gas_response,
    mock_import_statistics,
    patch_hourly_now,
    patch_recorder_days,
    entry_factory,
):
    """Gas consumption is imported alongside electricity when the API returns gas data."""
    dt_util.set_default_time_zone(timezone.utc)
    hass.config.components.add("recorder")
    entry = entry_factory("abc123_gas")

    mock_api(consumptions={"2026-03-27": consumptions_hour_with_gas_response})

    with (
        patch_hourly_now(datetime(2026, 3, 28, 16, 0, tzinfo=UTC)),
        patch_recorder_days({}),
    ):
        async with GreenchoiceApi("fake_user", "fake_password") as api:
            res = await async_import_yesterday_hourly_statistics(
                hass, api=api, entry=entry
            )

    assert res is not None
    assert res.imported is True
    assert res.date.isoformat() == "2026-03-27"
    assert res.points == 24
    # consumption + feed-in + gas = 3 calls
    assert mock_import_statistics.call_count == 3

    # electricity consumption: first two cumulative sums (0.422, 0.422+0.479)
    consumption_stats = mock_import_statistics.call_args_list[0].args[2]
    assert stat_sum(consumption_stats[0]) == pytest.approx(0.422)
    assert stat_sum(consumption_stats[1]) == pytest.approx(0.901)

    # gas: first two cumulative sums (0.005, 0.005+0.004); total across 24h = 0.991
    gas_stats = mock_import_statistics.call_args_list[2].args[2]
    assert stat_sum(gas_stats[0]) == pytest.approx(0.005)
    assert stat_sum(gas_stats[1]) == pytest.approx(0.009)
    assert stat_sum(gas_stats[-1]) == pytest.approx(0.991)


@pytest.mark.asyncio
async def test_import_electricity_only_does_not_call_gas(
    hass,
    mock_api,
    consumptions_hour_response,
    mock_import_statistics,
    patch_hourly_now,
    patch_recorder_days,
    entry_factory,
):
    """When the API returns no gas data, only 2 import calls are made (no gas call)."""
    dt_util.set_default_time_zone(timezone.utc)
    hass.config.components.add("recorder")
    entry = entry_factory("abc123_elec_only")

    mock_api(consumptions={"2026-03-27": consumptions_hour_response})

    with (
        patch_hourly_now(datetime(2026, 3, 28, 16, 0, tzinfo=UTC)),
        patch_recorder_days({}),
    ):
        async with GreenchoiceApi("fake_user", "fake_password") as api:
            res = await async_import_yesterday_hourly_statistics(
                hass, api=api, entry=entry
            )

    assert res is not None
    assert res.imported is True
    assert mock_import_statistics.call_count == 2  # consumption + feed-in only


@pytest.mark.asyncio
async def test_reimport_hourly_statistics_from(
    hass,
    mock_api,
    mock_import_statistics,
    patch_hourly_now,
    patch_recorder_days,
    entry_factory,
):
    """Reimport processes all days from start_date to yesterday, anchoring sums to
    the recorder value of the day immediately before start_date."""
    dt_util.set_default_time_zone(timezone.utc)
    hass.config.components.add("recorder")
    entry = entry_factory("abc123_reimport")

    day_26_consumption, day_27_consumption = 10.0, 6.0
    prior_day_sum = 100.0  # recorder sum for March 25 (day before start_date)

    mock_api(
        consumptions={
            "2026-03-26": make_consumptions_payload("2026-03-26", day_26_consumption),
            "2026-03-27": make_consumptions_payload("2026-03-27", day_27_consumption),
        }
    )

    with (
        patch_hourly_now(datetime(2026, 3, 28, 16, 0, tzinfo=UTC)),
        patch_recorder_days({date(2026, 3, 25): prior_day_sum}),
    ):
        async with GreenchoiceApi("fake_user", "fake_password") as api:
            total_points = await async_reimport_hourly_statistics_from(
                hass, api=api, entry=entry, start_date=date(2026, 3, 26)
            )

    assert total_points == 2
    assert mock_import_statistics.call_count == 4  # consumption + feed-in for each day

    # Cumulative sums are anchored to March 25's recorder value (prior_day_sum).
    assert stat_sum(
        mock_import_statistics.call_args_list[0].args[2][0]
    ) == pytest.approx(prior_day_sum + day_26_consumption)
    assert stat_sum(
        mock_import_statistics.call_args_list[2].args[2][0]
    ) == pytest.approx(prior_day_sum + day_26_consumption + day_27_consumption)


@pytest.mark.asyncio
async def test_reimport_raises_for_future_start_date(
    hass,
    mock_api,
    patch_hourly_now,
    entry_factory,
):
    """Passing today or a future date as start_date raises ValueError."""
    hass.config.components.add("recorder")
    entry = entry_factory("abc123_future")
    mock_api()

    with patch_hourly_now(datetime(2026, 3, 28, 16, 0, tzinfo=UTC)):
        async with GreenchoiceApi("fake_user", "fake_password") as api:
            with pytest.raises(ValueError):
                await async_reimport_hourly_statistics_from(
                    hass, api=api, entry=entry, start_date=date(2026, 3, 28)  # today
                )

