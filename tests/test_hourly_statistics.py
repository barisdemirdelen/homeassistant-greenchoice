from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.greenchoice.api import GreenchoiceApi
from custom_components.greenchoice.ha_external_statistics import (
    recorder as _recorder_mod,
)
from custom_components.greenchoice.ha_external_statistics.recorder import (
    async_get_last_sum,
)
from custom_components.greenchoice.sensor import GreenchoiceDataUpdateCoordinator
from tests.conftest import make_consumptions_payload, stat_sum

# Anchor "today" to a fixed date so API mocks with hardcoded dates are stable.
_TODAY = date(2026, 3, 28)
_YESTERDAY = date(2026, 3, 27)


_PATCH_GET_INSTANCE = f"{_recorder_mod.__name__}.get_instance"


def _make_coordinator(hass, entry):
    api = GreenchoiceApi("fake_user", "fake_password")
    return GreenchoiceDataUpdateCoordinator(hass, api, entry)


async def _run_update(hass, entry, *, first_run=False):
    """Run one statistics update cycle. first_run=True → backfill, False → retry."""
    coordinator = _make_coordinator(hass, entry)
    coordinator._stats_backfilled = not first_run
    async with coordinator.api:
        await coordinator.async_run_statistics_update()
    return coordinator


async def _run_reimport(hass, entry, start_date):
    coordinator = _make_coordinator(hass, entry)
    await coordinator.async_force_reimport(start_date)
    return coordinator


def _stat_id(m):
    return m["statistic_id"] if isinstance(m, dict) else m.statistic_id


def _source(m):
    return m["source"] if isinstance(m, dict) else m.source


@pytest.mark.asyncio
async def test_import_imports_yesterday(
    hass,
    mock_api,
    consumptions_hour_response,
    mock_import_statistics,
    patch_today,
    patch_recorder_days,
    entry_factory,
):
    """The previous day's data is imported and statistics metadata is correct."""
    hass.config.components.add("recorder")
    entry = entry_factory("abc123")
    mock_api(consumptions={"2026-03-27": consumptions_hour_response})

    with patch_today(_TODAY), patch_recorder_days({}):
        await _run_update(hass, entry)

    # consumption + feed-in + elec_cost + feed_in_comp (no gas)
    assert mock_import_statistics.call_count == 4

    consumption_meta = mock_import_statistics.call_args_list[0].args[1]
    feed_in_meta = mock_import_statistics.call_args_list[1].args[1]
    assert _stat_id(consumption_meta) == "greenchoice:my_home_electricity_consumption"
    assert _source(consumption_meta) == "greenchoice"
    assert _stat_id(feed_in_meta) == "greenchoice:my_home_electricity_feed_in"

    consumption_stats = mock_import_statistics.call_args_list[0].args[2]
    assert stat_sum(consumption_stats[0]) == pytest.approx(0.458)
    assert stat_sum(consumption_stats[1]) == pytest.approx(0.530)

    feed_in_stats = mock_import_statistics.call_args_list[1].args[2]
    assert stat_sum(feed_in_stats[0]) == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_import_first_run_backfills_and_chains_sums(
    hass,
    mock_api,
    mock_import_statistics,
    patch_today,
    patch_recorder_days,
    entry_factory,
):
    """first_run=True seeds from the recorder and chains sums across consecutive days."""
    hass.config.components.add("recorder")
    entry = entry_factory("abc123_backfill")

    day_26_consumption, day_27_consumption = 10.0, 6.0
    prior_sum = 100.0  # recorder end-of-day sum for March 25

    mock_api(
        consumptions={
            "2026-03-26": make_consumptions_payload("2026-03-26", day_26_consumption),
            "2026-03-27": make_consumptions_payload("2026-03-27", day_27_consumption),
        }
    )

    with patch_today(_TODAY), patch_recorder_days({date(2026, 3, 25): prior_sum}):
        await _run_update(hass, entry, first_run=True)

    # consumption + feed-in + elec_cost + feed_in_comp per day, 2 days
    assert mock_import_statistics.call_count == 8

    # March 26 seeded from March 25 recorder sum.
    assert stat_sum(
        mock_import_statistics.call_args_list[0].args[2][0]
    ) == pytest.approx(prior_sum + day_26_consumption)

    # March 27 chains from March 26 end-of-day sum (no extra DB query).
    assert stat_sum(
        mock_import_statistics.call_args_list[4].args[2][0]
    ) == pytest.approx(prior_sum + day_26_consumption + day_27_consumption)


@pytest.mark.asyncio
async def test_import_sums_seeded_from_recorder(
    hass,
    mock_api,
    mock_import_statistics,
    patch_today,
    patch_recorder_days,
    entry_factory,
):
    """Cumulative sums are seeded from the recorder value of the day before the range."""
    hass.config.components.add("recorder")
    entry = entry_factory("abc123_seed")

    prior_sum = 42.0
    day_consumption = 8.0

    mock_api(
        consumptions={
            "2026-03-27": make_consumptions_payload("2026-03-27", day_consumption)
        }
    )

    with patch_today(_TODAY), patch_recorder_days({date(2026, 3, 26): prior_sum}):
        await _run_update(hass, entry)

    consumption_stats = mock_import_statistics.call_args_list[0].args[2]
    assert stat_sum(consumption_stats[0]) == pytest.approx(prior_sum + day_consumption)


@pytest.mark.asyncio
async def test_import_empty_api_response(
    hass,
    mock_api,
    mock_import_statistics,
    patch_today,
    patch_recorder_days,
    entry_factory,
):
    """If the API returns no data for all days, nothing is imported."""
    hass.config.components.add("recorder")
    entry = entry_factory("abc123_empty")
    mock_api(consumptions={})

    with patch_today(_TODAY), patch_recorder_days({}):
        await _run_update(hass, entry)

    assert mock_import_statistics.call_count == 0


@pytest.mark.asyncio
async def test_import_with_gas(
    hass,
    mock_api,
    consumptions_hour_with_gas_response,
    mock_import_statistics,
    patch_today,
    patch_recorder_days,
    entry_factory,
):
    """Gas consumption is imported alongside electricity when the API returns gas data."""
    hass.config.components.add("recorder")
    entry = entry_factory("abc123_gas")
    mock_api(consumptions={"2026-03-27": consumptions_hour_with_gas_response})

    with patch_today(_TODAY), patch_recorder_days({}):
        await _run_update(hass, entry)

    # consumption + feed-in + elec_cost + feed_in_comp + gas + gas_cost
    assert mock_import_statistics.call_count == 6

    consumption_stats = mock_import_statistics.call_args_list[0].args[2]
    assert stat_sum(consumption_stats[0]) == pytest.approx(0.422)
    assert stat_sum(consumption_stats[1]) == pytest.approx(0.901)

    gas_stats = mock_import_statistics.call_args_list[4].args[2]
    assert stat_sum(gas_stats[0]) == pytest.approx(0.005)
    assert stat_sum(gas_stats[1]) == pytest.approx(0.009)
    assert stat_sum(gas_stats[-1]) == pytest.approx(0.991)


@pytest.mark.asyncio
async def test_import_feed_in_is_positive(
    hass,
    mock_api,
    mock_import_statistics,
    patch_today,
    patch_recorder_days,
    entry_factory,
):
    """API returns negative feed-in values; imported stats must be positive."""
    hass.config.components.add("recorder")
    entry = entry_factory("abc123_feed_in_sign")

    mock_api(
        consumptions={
            "2026-03-27": make_consumptions_payload(
                "2026-03-27", total_delivery=5.0, total_feed_in=-3.0
            )
        }
    )

    with patch_today(_TODAY), patch_recorder_days({}):
        await _run_update(hass, entry)

    feed_in_stats = mock_import_statistics.call_args_list[1].args[2]
    assert stat_sum(feed_in_stats[0]) == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_import_cost_stats(
    hass,
    mock_api,
    consumptions_hour_with_gas_response,
    mock_import_statistics,
    patch_today,
    patch_recorder_days,
    entry_factory,
):
    """Cost statistics are computed correctly from totalDeliveryCosts + totalFixedCosts."""
    hass.config.components.add("recorder")
    entry = entry_factory("abc123_costs")
    mock_api(consumptions={"2026-03-27": consumptions_hour_with_gas_response})

    with patch_today(_TODAY), patch_recorder_days({}):
        await _run_update(hass, entry)

    elec_cost_stats = mock_import_statistics.call_args_list[2].args[2]
    feed_in_comp_stats = mock_import_statistics.call_args_list[3].args[2]
    gas_cost_stats = mock_import_statistics.call_args_list[5].args[2]

    assert stat_sum(elec_cost_stats[0]) == pytest.approx(0.10897, abs=1e-4)
    assert stat_sum(feed_in_comp_stats[0]) == pytest.approx(0.0)
    assert stat_sum(gas_cost_stats[0]) == pytest.approx(0.04852, abs=1e-4)

    elec_cost_meta = mock_import_statistics.call_args_list[2].args[1]
    feed_in_comp_meta = mock_import_statistics.call_args_list[3].args[1]
    gas_cost_meta = mock_import_statistics.call_args_list[5].args[1]
    assert (
        _stat_id(elec_cost_meta) == "greenchoice:my_home_electricity_consumption_cost"
    )
    assert (
        _stat_id(feed_in_comp_meta)
        == "greenchoice:my_home_electricity_feed_in_compensation"
    )
    assert _stat_id(gas_cost_meta) == "greenchoice:my_home_gas_consumption_cost"


@pytest.mark.asyncio
async def test_async_get_last_sum_handles_dict_with_float_start(hass):
    """Regression: recorder may return 'start' as a Unix timestamp (float).

    async_get_last_sum must extract 'sum' correctly regardless of 'start' type.
    """

    statistic_id = "greenchoice:my_home_electricity_consumption"
    march_27_23_utc = datetime(2026, 3, 27, 23, 0, tzinfo=UTC)
    fake_stats = {statistic_id: [{"start": march_27_23_utc.timestamp(), "sum": 16.414}]}

    with patch(_PATCH_GET_INSTANCE) as mock_get_instance:
        mock_instance = Mock()
        mock_instance.async_add_executor_job = AsyncMock(return_value=fake_stats)
        mock_get_instance.return_value = mock_instance

        result = await async_get_last_sum(
            hass, statistic_id, datetime(2026, 3, 28, 0, 0, tzinfo=UTC)
        )

    assert result == pytest.approx(16.414)


@pytest.mark.asyncio
async def test_reimport_from_anchors_sums_and_chains(
    hass,
    mock_api,
    mock_import_statistics,
    patch_today,
    patch_recorder_days,
    entry_factory,
):
    """Reimport anchors sums to the recorder value before start_date and chains forward."""
    hass.config.components.add("recorder")
    entry = entry_factory("abc123_reimport")

    day_26_consumption, day_27_consumption = 10.0, 6.0
    prior_sum = 100.0

    mock_api(
        consumptions={
            "2026-03-26": make_consumptions_payload("2026-03-26", day_26_consumption),
            "2026-03-27": make_consumptions_payload("2026-03-27", day_27_consumption),
        }
    )

    with patch_today(_TODAY), patch_recorder_days({date(2026, 3, 25): prior_sum}):
        await _run_reimport(hass, entry, start_date=date(2026, 3, 26))

    # consumption + feed-in + elec_cost + feed_in_comp per day, 2 days
    assert mock_import_statistics.call_count == 8

    assert stat_sum(
        mock_import_statistics.call_args_list[0].args[2][0]
    ) == pytest.approx(prior_sum + day_26_consumption)
    assert stat_sum(
        mock_import_statistics.call_args_list[4].args[2][0]
    ) == pytest.approx(prior_sum + day_26_consumption + day_27_consumption)


@pytest.mark.asyncio
async def test_reimport_ignores_today_or_future(
    hass,
    mock_api,
    mock_import_statistics,
    patch_today,
    entry_factory,
):
    """Passing today or a future date as start_date is a no-op — nothing imported."""
    hass.config.components.add("recorder")
    entry = entry_factory("abc123_future")
    mock_api()

    with patch_today(_TODAY):
        await _run_reimport(hass, entry, start_date=_TODAY)

    assert mock_import_statistics.call_count == 0
