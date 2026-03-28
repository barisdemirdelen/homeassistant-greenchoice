from __future__ import annotations

import json
from datetime import UTC, date, datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.const import CONF_NAME
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.greenchoice.const import DOMAIN
from custom_components.greenchoice.hourly_statistics import (
    async_import_yesterday_hourly_statistics,
    _get_days_with_data,
    hourly_consumption_entity_id,
)
from custom_components.greenchoice.model import Consumptions, Preferences

_EMPTY_CONSUMPTIONS = {
    "interval": "Hour",
    "start": "2026-03-21T00:00:00",
    "end": "2026-03-22T00:00:00",
    "consumptionCosts": [],
}


@pytest.mark.asyncio
async def test_import_yesterday_hourly_statistics_imports_and_is_idempotent(hass):
    # Ensure deterministic timezone/day calculations.
    dt_util.set_default_time_zone(timezone.utc)
    hass.config.components.add("recorder")

    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="abc123",
        title="Greenchoice (Test)",
        data={CONF_NAME: "My Home"},
    )
    entry.add_to_hass(hass)

    fixture = (
        Path(__file__).parent / "test_data" / "test_consumptions_hour.json"
    ).read_text()
    consumptions_payload = json.loads(fixture)

    class ApiStub:
        customer_number = None
        agreement_id = None

        async def get_preferences(self):
            return Preferences.model_validate(
                {
                    "accountId": "00000000-0000-0000-0000-000000000000",
                    "customerNumber": 2222,
                    "agreementId": 1111,
                }
            )

        async def get_consumptions(self, *, interval, start):
            assert interval == "Hour"
            if start.isoformat() == "2026-03-27":
                return Consumptions.model_validate(consumptions_payload)
            # All other days in the scan window have no data yet.
            return Consumptions.model_validate(
                {
                    "interval": "Hour",
                    "start": start.isoformat(),
                    "end": (start + __import__("datetime").timedelta(days=1)).isoformat(),
                    "consumptionCosts": [],
                }
            )

    api = ApiStub()

    fixed_now_early = datetime(2026, 3, 28, 4, 0, tzinfo=UTC)
    fixed_now_later = datetime(2026, 3, 28, 16, 0, tzinfo=UTC)

    # 1. First call at 04:00 with only yesterday missing -> should skip (too early).
    #    Older days all have data, so there is nothing else to backfill.
    all_days_except_yesterday = {
        date(2026, 3, 21) + __import__("datetime").timedelta(days=i): 1.0
        for i in range(6)  # March 21-26 present, March 27 (yesterday) absent
    }
    with (
        patch(
            "custom_components.greenchoice.hourly_statistics.dt_util.now",
            return_value=fixed_now_early,
        ),
        patch(
            "homeassistant.components.recorder.statistics.async_import_statistics",
            new=Mock(),
        ) as mock_import,
        patch(
            "custom_components.greenchoice.hourly_statistics._get_days_with_data",
            new=AsyncMock(return_value=all_days_except_yesterday),
        ),
    ):
        res_early = await async_import_yesterday_hourly_statistics(
            hass, api=api, entry=entry
        )
        assert res_early is None
        assert mock_import.call_count == 0

    # 2. Second call at 16:00 -> should import only 2026-03-27 (the one day with data).
    #    _get_days_with_data is patched to return an empty dict, simulating that the
    #    recorder has no existing statistics (e.g. first run after a multi-day outage).
    with (
        patch(
            "custom_components.greenchoice.hourly_statistics.dt_util.now",
            return_value=fixed_now_later,
        ),
        patch(
            "homeassistant.components.recorder.statistics.async_import_statistics",
            new=Mock(),
        ) as mock_import,
        patch(
            "custom_components.greenchoice.hourly_statistics._get_days_with_data",
            new=AsyncMock(return_value={}),
        ),
    ):
        res = await async_import_yesterday_hourly_statistics(hass, api=api, entry=entry)

        assert res is not None
        assert res.imported is True
        assert res.date.isoformat() == "2026-03-27"
        assert res.points == 24
        assert mock_import.call_count == 2  # consumption + feed-in

        # Ensure statistic_id matches entity_id (required for Energy dashboard selection).
        consumption_meta = mock_import.call_args_list[0].args[1]
        feed_in_meta = mock_import.call_args_list[1].args[1]

        def _stat_id(meta):
            return meta["statistic_id"] if isinstance(meta, dict) else meta.statistic_id

        def _source(meta):
            return meta["source"] if isinstance(meta, dict) else meta.source

        assert (
            _stat_id(consumption_meta)
            == "sensor.my_home_electricity_consumption_hourly"
        )
        assert _source(consumption_meta) == "recorder"

        assert _stat_id(feed_in_meta) == "sensor.my_home_electricity_feed_in_hourly"
        assert _source(feed_in_meta) == "recorder"

        def _sum(stat):
            return stat["sum"] if isinstance(stat, dict) else stat.sum

        # Consumption: 0.458 (hour 00) then 0.072 (hour 01) -> cumulative 0.530
        consumption_stats = mock_import.call_args_list[0].args[2]
        assert float(_sum(consumption_stats[0])) == pytest.approx(0.458)
        assert float(_sum(consumption_stats[1])) == pytest.approx(0.530)

        # Feed-in: 0 (hour 00) then 0 (hour 01) -> cumulative 0.0 (first feed-in at hour 06)
        feed_in_stats = mock_import.call_args_list[1].args[2]
        assert float(_sum(feed_in_stats[0])) == pytest.approx(0.0)
        assert float(_sum(feed_in_stats[1])) == pytest.approx(0.0)

    # 3. Third call (idempotency): recorder now reports all days as having data.
    #    The function should find no missing days and return without importing.
    all_days_present = {
        date(2026, 3, 21) + __import__("datetime").timedelta(days=i): 1.0
        for i in range(7)
    }
    with (
        patch(
            "custom_components.greenchoice.hourly_statistics.dt_util.now",
            return_value=fixed_now_later,
        ),
        patch(
            "homeassistant.components.recorder.statistics.async_import_statistics",
            new=Mock(),
        ) as mock_import_idempotent,
        patch(
            "custom_components.greenchoice.hourly_statistics._get_days_with_data",
            new=AsyncMock(return_value=all_days_present),
        ),
    ):
        res2 = await async_import_yesterday_hourly_statistics(
            hass, api=api, entry=entry
        )
        assert res2 is not None
        assert res2.imported is False
        assert mock_import_idempotent.call_count == 0


@pytest.mark.asyncio
async def test_import_before_13_still_backfills_older_gaps(hass):
    """Before 13:00, yesterday is deferred but older missing days are still imported."""
    dt_util.set_default_time_zone(timezone.utc)
    hass.config.components.add("recorder")

    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="abc123_early",
        title="Greenchoice (Test Early)",
        data={CONF_NAME: "My Home"},
    )
    entry.add_to_hass(hass)

    # Recorder has data up to March 25; March 26 and 27 (yesterday) are both missing.
    recorder_has_data = {
        date(2026, 3, 21) + __import__("datetime").timedelta(days=i): float(i + 1)
        for i in range(5)  # March 21-25 present
    }

    class ApiStub:
        customer_number = 2222
        agreement_id = 1111

        async def get_preferences(self):
            return Preferences.model_validate(
                {
                    "accountId": "00000000-0000-0000-0000-000000000000",
                    "customerNumber": 2222,
                    "agreementId": 1111,
                }
            )

        async def get_consumptions(self, *, interval, start):
            assert interval == "Hour"
            if start == date(2026, 3, 26):
                return Consumptions.model_validate(
                    {
                        "interval": "Hour",
                        "start": "2026-03-26T00:00:00",
                        "end": "2026-03-27T00:00:00",
                        "consumptionCosts": [
                            {
                                "consumedOn": "2026-03-26T00:00:00",
                                "electricity": {
                                    "totalDeliveryConsumption": 5.0,
                                    "totalFeedInConsumption": 0,
                                    "hasConsumption": True,
                                },
                                "hasConsumption": True,
                            }
                        ],
                    }
                )
            # Yesterday (March 27) should NOT be requested before 13:00.
            raise AssertionError(f"Unexpected API call for {start}")

    api = ApiStub()
    # 10:00 local — before the 13:00 gate.
    fixed_now = datetime(2026, 3, 28, 10, 0, tzinfo=UTC)

    with (
        patch(
            "custom_components.greenchoice.hourly_statistics.dt_util.now",
            return_value=fixed_now,
        ),
        patch(
            "homeassistant.components.recorder.statistics.async_import_statistics",
            new=Mock(),
        ) as mock_import,
        patch(
            "custom_components.greenchoice.hourly_statistics._get_days_with_data",
            new=AsyncMock(return_value=recorder_has_data),
        ),
    ):
        res = await async_import_yesterday_hourly_statistics(hass, api=api, entry=entry)

        # March 26 should have been imported even though it's before 13:00.
        assert res is not None
        assert res.imported is True
        assert res.date == date(2026, 3, 26)
        assert res.points == 1
        # March 27 (yesterday) was NOT imported — deferred until after 13:00.
        assert mock_import.call_count == 2  # consumption + feed-in for March 26 only


@pytest.mark.asyncio
async def test_import_yesterday_hourly_statistics_backfills_gap(hass):
    """When the recorder shows a gap in the middle of the scan window (e.g. two days
    missing after a multi-day outage), all missing days are imported and cumulative
    sums correctly chain across the gap.
    """
    dt_util.set_default_time_zone(timezone.utc)
    hass.config.components.add("recorder")

    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="abc123_gap",
        title="Greenchoice (Test Gap)",
        data={CONF_NAME: "My Home"},
    )
    entry.add_to_hass(hass)

    # Simulate a two-day outage: March 26 and 27 are missing.
    # The recorder has data up to and including March 25 with end-of-day sum = 100.
    recorder_has_data = {
        date(2026, 3, 21): 40.0,
        date(2026, 3, 22): 55.0,
        date(2026, 3, 23): 68.0,
        date(2026, 3, 24): 82.0,
        date(2026, 3, 25): 100.0,
        # March 26 and 27 are absent (the gap).
    }

    day_26_consumption = 10.0
    day_27_consumption = 6.0

    class ApiStub:
        customer_number = 2222
        agreement_id = 1111

        async def get_preferences(self):
            return Preferences.model_validate(
                {
                    "accountId": "00000000-0000-0000-0000-000000000000",
                    "customerNumber": 2222,
                    "agreementId": 1111,
                }
            )

        async def get_consumptions(self, *, interval, start):
            assert interval == "Hour"
            if start == date(2026, 3, 26):
                return Consumptions.model_validate(
                    {
                        "interval": "Hour",
                        "start": "2026-03-26T00:00:00",
                        "end": "2026-03-27T00:00:00",
                        "consumptionCosts": [
                            {
                                "consumedOn": "2026-03-26T00:00:00",
                                "electricity": {
                                    "totalDeliveryConsumption": day_26_consumption,
                                    "totalFeedInConsumption": 0,
                                    "hasConsumption": True,
                                },
                                "hasConsumption": True,
                            }
                        ],
                    }
                )
            if start == date(2026, 3, 27):
                return Consumptions.model_validate(
                    {
                        "interval": "Hour",
                        "start": "2026-03-27T00:00:00",
                        "end": "2026-03-28T00:00:00",
                        "consumptionCosts": [
                            {
                                "consumedOn": "2026-03-27T00:00:00",
                                "electricity": {
                                    "totalDeliveryConsumption": day_27_consumption,
                                    "totalFeedInConsumption": 0,
                                    "hasConsumption": True,
                                },
                                "hasConsumption": True,
                            }
                        ],
                    }
                )
            return Consumptions.model_validate(
                {
                    "interval": "Hour",
                    "start": start.isoformat(),
                    "end": (start + __import__("datetime").timedelta(days=1)).isoformat(),
                    "consumptionCosts": [],
                }
            )

    api = ApiStub()
    fixed_now = datetime(2026, 3, 28, 16, 0, tzinfo=UTC)

    with (
        patch(
            "custom_components.greenchoice.hourly_statistics.dt_util.now",
            return_value=fixed_now,
        ),
        patch(
            "homeassistant.components.recorder.statistics.async_import_statistics",
            new=Mock(),
        ) as mock_import,
        patch(
            "custom_components.greenchoice.hourly_statistics._get_days_with_data",
            # side_effect returns a fresh dict per call so consumption and feed-in
            # day-sum mappings don't share the same object and corrupt each other.
            side_effect=[dict(recorder_has_data), {}],
        ),
    ):
        res = await async_import_yesterday_hourly_statistics(hass, api=api, entry=entry)

        assert res is not None
        assert res.imported is True
        assert res.date == date(2026, 3, 27)
        assert res.points == 2  # one point per missing day
        assert mock_import.call_count == 4  # consumption + feed-in, twice (once per day)

        def _sum(stat):
            return stat["sum"] if isinstance(stat, dict) else stat.sum

        # March 26 should start from March 25's end sum (100) and add day_26_consumption.
        march_26_consumption_stats = mock_import.call_args_list[0].args[2]
        assert float(_sum(march_26_consumption_stats[0])) == pytest.approx(
            100.0 + day_26_consumption
        )

        # March 27 should chain on top of March 26's end sum.
        march_27_consumption_stats = mock_import.call_args_list[2].args[2]
        assert float(_sum(march_27_consumption_stats[0])) == pytest.approx(
            100.0 + day_26_consumption + day_27_consumption
        )


@pytest.mark.asyncio
async def test_import_corrects_stale_sums_after_gap(hass):
    """When a gap is backfilled, days that already exist in the recorder but come
    AFTER the gap must be re-imported with corrected cumulative sums.  Without this,
    the Energy dashboard shows a huge (often negative) spike at the start of the first
    day after the gap because its sums were computed from a different baseline.
    """
    dt_util.set_default_time_zone(timezone.utc)
    hass.config.components.add("recorder")

    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="abc123_stale",
        title="Greenchoice (Test Stale)",
        data={CONF_NAME: "My Home"},
    )
    entry.add_to_hass(hass)

    day_26_consumption = 10.0
    day_27_consumption = 6.0

    # Recorder: March 21-25 ok, March 26 MISSING, March 27 present but with a
    # stale sum that was computed without March 26 (wrong baseline).
    stale_sum_march_27 = 100.0 + day_27_consumption  # built on March 25 end sum, skipping March 26
    recorder_consumption = {
        date(2026, 3, 21): 40.0,
        date(2026, 3, 22): 55.0,
        date(2026, 3, 23): 68.0,
        date(2026, 3, 24): 82.0,
        date(2026, 3, 25): 100.0,
        # March 26 absent (gap)
        date(2026, 3, 27): stale_sum_march_27,
    }

    class ApiStub:
        customer_number = 2222
        agreement_id = 1111

        async def get_preferences(self):
            return Preferences.model_validate(
                {
                    "accountId": "00000000-0000-0000-0000-000000000000",
                    "customerNumber": 2222,
                    "agreementId": 1111,
                }
            )

        async def get_consumptions(self, *, interval, start):
            assert interval == "Hour"
            consumption = {
                date(2026, 3, 26): day_26_consumption,
                date(2026, 3, 27): day_27_consumption,
            }.get(start, 0.0)
            if consumption == 0.0:
                return Consumptions.model_validate(
                    {
                        "interval": "Hour",
                        "start": start.isoformat(),
                        "end": (start + __import__("datetime").timedelta(days=1)).isoformat(),
                        "consumptionCosts": [],
                    }
                )
            return Consumptions.model_validate(
                {
                    "interval": "Hour",
                    "start": f"{start}T00:00:00",
                    "end": f"{start + __import__('datetime').timedelta(days=1)}T00:00:00",
                    "consumptionCosts": [
                        {
                            "consumedOn": f"{start}T00:00:00",
                            "electricity": {
                                "totalDeliveryConsumption": consumption,
                                "totalFeedInConsumption": 0,
                                "hasConsumption": True,
                            },
                            "hasConsumption": True,
                        }
                    ],
                }
            )

    api = ApiStub()
    fixed_now = datetime(2026, 3, 28, 16, 0, tzinfo=UTC)

    with (
        patch(
            "custom_components.greenchoice.hourly_statistics.dt_util.now",
            return_value=fixed_now,
        ),
        patch(
            "homeassistant.components.recorder.statistics.async_import_statistics",
            new=Mock(),
        ) as mock_import,
        patch(
            "custom_components.greenchoice.hourly_statistics._get_days_with_data",
            side_effect=[dict(recorder_consumption), {}],
        ),
    ):
        res = await async_import_yesterday_hourly_statistics(hass, api=api, entry=entry)

        assert res is not None
        assert res.imported is True
        # Both March 26 (gap) and March 27 (stale sum correction) are processed.
        assert res.points == 2
        # 4 calls: consumption + feed-in for March 26, then same for March 27.
        assert mock_import.call_count == 4

        def _sum(stat):
            return stat["sum"] if isinstance(stat, dict) else stat.sum

        # March 26: correct sum = March 25 end (100) + day_26 (10) = 110.
        march_26_stats = mock_import.call_args_list[0].args[2]
        assert float(_sum(march_26_stats[0])) == pytest.approx(100.0 + day_26_consumption)

        # March 27: correct sum = March 26 end (110) + day_27 (6) = 116,
        # NOT the stale value of 106 that was in the recorder.
        march_27_stats = mock_import.call_args_list[2].args[2]
        assert float(_sum(march_27_stats[0])) == pytest.approx(
            100.0 + day_26_consumption + day_27_consumption
        )
        assert float(_sum(march_27_stats[0])) != pytest.approx(stale_sum_march_27)


@pytest.mark.asyncio
async def test_import_yesterday_hourly_statistics_retries_on_empty(hass):
    """Test that if data is empty, we do NOT save last sums, allowing retries."""
    dt_util.set_default_time_zone(timezone.utc)
    hass.config.components.add("recorder")

    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="abc123_empty",
        title="Greenchoice (Test Empty)",
        data={CONF_NAME: "My Home"},
    )
    entry.add_to_hass(hass)

    class ApiStubEmpty:
        customer_number = 2222
        agreement_id = 1111

        async def get_preferences(self):
            return Preferences.model_validate(
                {
                    "accountId": "00000000-0000-0000-0000-000000000000",
                    "customerNumber": 2222,
                    "agreementId": 1111,
                }
            )

        async def get_consumptions(self, *, interval, start):
            return Consumptions.model_validate(
                {
                    "interval": "Hour",
                    "start": start.isoformat(),
                    "end": (start + __import__("datetime").timedelta(days=1)).isoformat(),
                    "consumptionCosts": [],
                }
            )

    api = ApiStubEmpty()
    fixed_now = datetime(2026, 3, 28, 15, 0, tzinfo=UTC)

    with (
        patch(
            "custom_components.greenchoice.hourly_statistics.dt_util.now",
            return_value=fixed_now,
        ),
        patch(
            "custom_components.greenchoice.hourly_statistics._get_days_with_data",
            new=AsyncMock(return_value={}),
        ),
        patch("homeassistant.helpers.storage.Store.async_save") as mock_save,
    ):
        res = await async_import_yesterday_hourly_statistics(hass, api=api, entry=entry)

        assert res is not None
        assert res.imported is False
        assert res.points == 0

        # KEY ASSERTION: async_save should NOT be called because no points were imported.
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

    # Build a stat row where start is a float (Unix timestamp) instead of a datetime.
    march_27_00_utc = datetime(2026, 3, 27, 0, 0, tzinfo=UTC)
    march_27_23_utc = datetime(2026, 3, 27, 23, 0, tzinfo=UTC)

    fake_stats = {
        statistic_id: [
            {"start": march_27_00_utc.timestamp(), "sum": 5.0},
            {"start": march_27_23_utc.timestamp(), "sum": 16.414},
        ]
    }

    with patch(
        "homeassistant.components.recorder.get_instance"
    ) as mock_get_instance:
        mock_instance = Mock()
        mock_instance.async_add_executor_job = AsyncMock(return_value=fake_stats)
        mock_get_instance.return_value = mock_instance

        result = await _get_days_with_data(hass, statistic_id, target_date, target_date)

    # Should have found March 27 with its highest (last) sum value.
    assert target_date in result
    assert result[target_date] == pytest.approx(16.414)
