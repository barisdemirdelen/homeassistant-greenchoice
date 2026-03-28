from __future__ import annotations

import json
from datetime import UTC, datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from homeassistant.const import CONF_NAME
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.greenchoice.const import DOMAIN
from custom_components.greenchoice.hourly_statistics import (
    async_import_yesterday_hourly_statistics,
)
from custom_components.greenchoice.model import Preferences


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

        async def get_consumptions(self, *, interval, start, end):
            assert interval == "Hour"
            assert start.isoformat() == "2025-12-28"
            assert end.isoformat() == "2025-12-29"
            from custom_components.greenchoice.model import Consumptions

            return Consumptions.model_validate(consumptions_payload)

    api = ApiStub()

    fixed_now_early = datetime(2025, 12, 29, 4, 0, tzinfo=UTC)
    fixed_now_later = datetime(2025, 12, 29, 16, 0, tzinfo=UTC)

    # 1. First call at 04:00 -> should skip (too early)
    with (
        patch(
            "custom_components.greenchoice.hourly_statistics.dt_util.now",
            return_value=fixed_now_early,
        ),
        patch(
            "homeassistant.components.recorder.statistics.async_import_statistics",
            new=Mock(),
        ) as mock_import,
    ):
        res_early = await async_import_yesterday_hourly_statistics(
            hass, api=api, entry=entry
        )
        assert res_early is None
        assert mock_import.call_count == 0

    # 2. Second call at 15:00 -> should run
    with (
        patch(
            "custom_components.greenchoice.hourly_statistics.dt_util.now",
            return_value=fixed_now_later,
        ),
        patch(
            "homeassistant.components.recorder.statistics.async_import_statistics",
            new=Mock(),
        ) as mock_import,
    ):
        res = await async_import_yesterday_hourly_statistics(hass, api=api, entry=entry)

        assert res is not None
        assert res.imported is True
        assert res.date.isoformat() == "2025-12-28"
        assert res.points == 2
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

        # Consumption: 0.49 then 0.001 -> cumulative 0.491
        consumption_stats = mock_import.call_args_list[0].args[2]
        assert float(_sum(consumption_stats[0])) == pytest.approx(0.49)
        assert float(_sum(consumption_stats[1])) == pytest.approx(0.491)

        # Feed-in: 0 then 0.853 -> cumulative 0.853
        feed_in_stats = mock_import.call_args_list[1].args[2]
        assert float(_sum(feed_in_stats[0])) == pytest.approx(0.0)
        assert float(_sum(feed_in_stats[1])) == pytest.approx(0.853)

        # Second call should be skipped (idempotent store guard).
        res2 = await async_import_yesterday_hourly_statistics(
            hass, api=api, entry=entry
        )
        assert res2 is not None
        assert res2.imported is False
        assert mock_import.call_count == 2


@pytest.mark.asyncio
async def test_import_yesterday_hourly_statistics_retries_on_empty(hass):
    """Test that if data is empty, we do NOT save last_imported, allowing retries."""
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

        async def get_consumptions(self, *, interval, start, end):
            from custom_components.greenchoice.model import Consumptions

            return Consumptions.model_validate(
                {
                    "interval": "Hour",
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "consumptionCosts": [],  # Empty list of points
                }
            )

    api = ApiStubEmpty()
    # 15:00 UTC = 16:00 CET, so well past 13:00 check
    fixed_now = datetime(2025, 12, 29, 15, 0, tzinfo=UTC)

    with (
        patch(
            "custom_components.greenchoice.hourly_statistics.dt_util.now",
            return_value=fixed_now,
        ),
        patch("homeassistant.helpers.storage.Store.async_save") as mock_save,
    ):
        # 1. First call: returns empty
        res = await async_import_yesterday_hourly_statistics(hass, api=api, entry=entry)

        assert res is not None
        assert res.imported is False
        assert res.points == 0

        # KEY ASSERTION: async_save should NOT be called because points=0
        mock_save.assert_not_called()
