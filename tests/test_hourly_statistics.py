from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.greenchoice.api import GreenchoiceApi
from custom_components.greenchoice.hourly_statistics import (
    _get_sum_before,
    async_import_hourly_statistics,
    async_reimport_hourly_statistics_from,
    hourly_statistic_id,
)
from tests.conftest import make_consumptions_payload, stat_sum

# Anchor "today" to a fixed date so API mocks with hardcoded dates are stable.
_TODAY = date(2026, 3, 28)
_YESTERDAY = date(2026, 3, 27)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run_import(hass, entry, first_run=False):
    async with GreenchoiceApi("fake_user", "fake_password") as api:
        return await async_import_hourly_statistics(
            hass, api=api, entry=entry, first_run=first_run
        )


async def _run_reimport(hass, entry, start_date):
    async with GreenchoiceApi("fake_user", "fake_password") as api:
        return await async_reimport_hourly_statistics_from(
            hass, api=api, entry=entry, start_date=start_date
        )


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
    patch_now,
    patch_recorder_days,
    entry_factory,
):
    """The previous day's data is imported and statistics metadata is correct."""
    hass.config.components.add("recorder")
    entry = entry_factory("abc123")
    mock_api(consumptions={"2026-03-27": consumptions_hour_response})

    with patch_now(_TODAY), patch_recorder_days({}):
        res = await _run_import(hass, entry)

    assert res is not None
    assert res.imported is True
    assert res.date == _YESTERDAY
    assert res.points == 24
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
    patch_now,
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

    with patch_now(_TODAY), patch_recorder_days({date(2026, 3, 25): prior_sum}):
        res = await _run_import(hass, entry, first_run=True)

    assert res is not None
    assert res.imported is True
    assert res.date == _YESTERDAY
    assert res.points == 2
    # consumption + feed-in + elec_cost + feed_in_comp per day, 2 days
    assert mock_import_statistics.call_count == 8

    # March 26 consumption is seeded from March 25's recorder sum.
    assert stat_sum(
        mock_import_statistics.call_args_list[0].args[2][0]
    ) == pytest.approx(prior_sum + day_26_consumption)

    # March 27 consumption chains from March 26's end-of-day sum (no extra DB query).
    # call order per day: consumption[0], feed-in[1], elec_cost[2], feed_in_comp[3]
    assert stat_sum(
        mock_import_statistics.call_args_list[4].args[2][0]
    ) == pytest.approx(prior_sum + day_26_consumption + day_27_consumption)


@pytest.mark.asyncio
async def test_import_sums_seeded_from_recorder(
    hass,
    mock_api,
    mock_import_statistics,
    patch_now,
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

    with patch_now(_TODAY), patch_recorder_days({date(2026, 3, 26): prior_sum}):
        res = await _run_import(hass, entry)

    assert res is not None
    assert res.imported is True
    consumption_stats = mock_import_statistics.call_args_list[0].args[2]
    assert stat_sum(consumption_stats[0]) == pytest.approx(prior_sum + day_consumption)


@pytest.mark.asyncio
async def test_import_empty_api_response(
    hass,
    mock_api,
    mock_import_statistics,
    patch_now,
    patch_recorder_days,
    entry_factory,
):
    """If the API returns no data for all days, nothing is imported and Store is not written."""
    hass.config.components.add("recorder")
    entry = entry_factory("abc123_empty")
    mock_api(consumptions={})

    with patch_now(_TODAY), patch_recorder_days({}):
        res = await _run_import(hass, entry)

    assert res is not None
    assert res.imported is False
    assert res.points == 0
    assert mock_import_statistics.call_count == 0


@pytest.mark.asyncio
async def test_import_with_gas(
    hass,
    mock_api,
    consumptions_hour_with_gas_response,
    mock_import_statistics,
    patch_now,
    patch_recorder_days,
    entry_factory,
):
    """Gas consumption is imported alongside electricity when the API returns gas data."""
    hass.config.components.add("recorder")
    entry = entry_factory("abc123_gas")
    mock_api(consumptions={"2026-03-27": consumptions_hour_with_gas_response})

    with patch_now(_TODAY), patch_recorder_days({}):
        res = await _run_import(hass, entry)

    assert res is not None
    assert res.imported is True
    assert res.points == 24
    # consumption + feed-in + elec_cost + feed_in_comp + gas + gas_cost
    assert mock_import_statistics.call_count == 6

    consumption_stats = mock_import_statistics.call_args_list[0].args[2]
    assert stat_sum(consumption_stats[0]) == pytest.approx(0.422)
    assert stat_sum(consumption_stats[1]) == pytest.approx(0.901)

    # gas is call index 4 (after consumption, feed-in, elec_cost, feed_in_comp)
    gas_stats = mock_import_statistics.call_args_list[4].args[2]
    assert stat_sum(gas_stats[0]) == pytest.approx(0.005)
    assert stat_sum(gas_stats[1]) == pytest.approx(0.009)
    assert stat_sum(gas_stats[-1]) == pytest.approx(0.991)


@pytest.mark.asyncio
async def test_import_feed_in_is_positive(
    hass,
    mock_api,
    mock_import_statistics,
    patch_now,
    patch_recorder_days,
    entry_factory,
):
    """API returns negative feed-in values; imported stats must be positive."""
    hass.config.components.add("recorder")
    entry = entry_factory("abc123_feed_in_sign")

    # API convention: feed-in consumption is negative (energy flowing back to grid).
    mock_api(
        consumptions={
            "2026-03-27": make_consumptions_payload(
                "2026-03-27", total_delivery=5.0, total_feed_in=-3.0
            )
        }
    )

    with patch_now(_TODAY), patch_recorder_days({}):
        await _run_import(hass, entry)

    # call order: [0] consumption, [1] feed-in
    feed_in_stats = mock_import_statistics.call_args_list[1].args[2]
    assert stat_sum(feed_in_stats[0]) == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_import_cost_stats(
    hass,
    mock_api,
    consumptions_hour_with_gas_response,
    mock_import_statistics,
    patch_now,
    patch_recorder_days,
    entry_factory,
):
    """Cost statistics are computed correctly from totalDeliveryCosts + totalFixedCosts."""
    hass.config.components.add("recorder")
    entry = entry_factory("abc123_costs")
    mock_api(consumptions={"2026-03-27": consumptions_hour_with_gas_response})

    with patch_now(_TODAY), patch_recorder_days({}):
        await _run_import(hass, entry)

    # call order: [0] consumption, [1] feed-in, [2] elec_cost, [3] feed_in_comp,
    #             [4] gas, [5] gas_cost
    elec_cost_stats = mock_import_statistics.call_args_list[2].args[2]
    feed_in_comp_stats = mock_import_statistics.call_args_list[3].args[2]
    gas_cost_stats = mock_import_statistics.call_args_list[5].args[2]

    # Hour 0: totalDeliveryCosts=0.11276, totalFixedCosts=-0.00379 → 0.10897
    assert stat_sum(elec_cost_stats[0]) == pytest.approx(0.10897, abs=1e-4)
    # Hour 0: totalFeedInCompensation=0.0, totalFeedInCosts=0.0 → 0.0
    assert stat_sum(feed_in_comp_stats[0]) == pytest.approx(0.0)
    # Hour 0: gas totalDeliveryCosts=0.00653, totalFixedCosts=0.04199 → 0.04852
    assert stat_sum(gas_cost_stats[0]) == pytest.approx(0.04852, abs=1e-4)

    elec_cost_meta = mock_import_statistics.call_args_list[2].args[1]
    feed_in_comp_meta = mock_import_statistics.call_args_list[3].args[1]
    gas_cost_meta = mock_import_statistics.call_args_list[5].args[1]
    assert _stat_id(elec_cost_meta) == "greenchoice:my_home_electricity_consumption_cost"
    assert _stat_id(feed_in_comp_meta) == "greenchoice:my_home_electricity_feed_in_compensation"
    assert _stat_id(gas_cost_meta) == "greenchoice:my_home_gas_consumption_cost"


@pytest.mark.asyncio
async def test_get_sum_before_handles_float_timestamps(hass):
    """Regression: newer HA recorder versions return 'start' as a Unix timestamp (float).

    _get_sum_before must not crash with 'float has no attribute tzinfo'.
    """
    statistic_id = hourly_statistic_id("My Home", "electricity_consumption")
    march_27_23_utc = datetime(2026, 3, 27, 23, 0, tzinfo=UTC)
    fake_stats = {statistic_id: [{"start": march_27_23_utc.timestamp(), "sum": 16.414}]}

    with patch(
        "custom_components.greenchoice.hourly_statistics.get_instance"
    ) as mock_get_instance:
        mock_instance = Mock()
        mock_instance.async_add_executor_job = AsyncMock(return_value=fake_stats)
        mock_get_instance.return_value = mock_instance

        result = await _get_sum_before(
            hass, statistic_id, datetime(2026, 3, 28, 0, 0, tzinfo=UTC)
        )

    assert result == pytest.approx(16.414)


@pytest.mark.asyncio
async def test_reimport_from_anchors_sums_and_chains(
    hass,
    mock_api,
    mock_import_statistics,
    patch_now,
    patch_recorder_days,
    entry_factory,
):
    """Reimport anchors sums to the recorder value before start_date and chains forward."""
    hass.config.components.add("recorder")
    entry = entry_factory("abc123_reimport")

    day_26_consumption, day_27_consumption = 10.0, 6.0
    prior_sum = 100.0  # recorder end-of-day sum for March 25

    mock_api(
        consumptions={
            "2026-03-26": make_consumptions_payload("2026-03-26", day_26_consumption),
            "2026-03-27": make_consumptions_payload("2026-03-27", day_27_consumption),
        }
    )

    with patch_now(_TODAY), patch_recorder_days({date(2026, 3, 25): prior_sum}):
        total_points = await _run_reimport(hass, entry, start_date=date(2026, 3, 26))

    assert total_points == 2
    # consumption + feed-in + elec_cost + feed_in_comp per day, 2 days
    assert mock_import_statistics.call_count == 8

    assert stat_sum(
        mock_import_statistics.call_args_list[0].args[2][0]
    ) == pytest.approx(prior_sum + day_26_consumption)
    # call order per day: consumption[0], feed-in[1], elec_cost[2], feed_in_comp[3]
    assert stat_sum(
        mock_import_statistics.call_args_list[4].args[2][0]
    ) == pytest.approx(prior_sum + day_26_consumption + day_27_consumption)


@pytest.mark.asyncio
async def test_reimport_raises_for_today_or_future(
    hass,
    mock_api,
    entry_factory,
):
    """Passing today or a future date as start_date raises ValueError."""
    hass.config.components.add("recorder")
    entry = entry_factory("abc123_future")
    mock_api()

    with pytest.raises(ValueError):
        await _run_reimport(hass, entry, start_date=date.today())
