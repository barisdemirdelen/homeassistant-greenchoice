"""Tests for ha_external_statistic.recorder helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.greenchoice.ha_external_statistics import (
    external_statistic as _ext_stat_mod,
)
from custom_components.greenchoice.ha_external_statistics import (
    recorder as _recorder_mod,
)
from custom_components.greenchoice.ha_external_statistics.external_statistic import (
    ExternalStatistic,
)
from custom_components.greenchoice.ha_external_statistics.recorder import (
    async_get_last_sum,
    async_inject_day,
)

_GET_INSTANCE_PATH = f"{_recorder_mod.__name__}.get_instance"
_SDP_PATH = f"{_recorder_mod.__name__}.statistics_during_period"
_ADD_STAT_PATH = f"{_ext_stat_mod.__name__}.async_add_external_statistics"


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@dataclass
class Entry:
    hour: int
    value: float


_DATE = date(2024, 3, 15)
_DAY_START = datetime(2024, 3, 15, 0, 0, tzinfo=UTC)


def _ts(entry: Entry, for_date: date) -> datetime:
    return datetime(
        for_date.year, for_date.month, for_date.day, entry.hour, 0, tzinfo=UTC
    )


def _make_stat(stat_id: str = "dom:stat") -> ExternalStatistic[Entry]:
    return ExternalStatistic(
        statistic_id=stat_id,
        name="Test",
        source="dom",
        unit_of_measurement="kWh",
        unit_class="energy",
        period_start_fn=_ts,
        value_fn=lambda e: e.value,
    )


# ---------------------------------------------------------------------------
# async_get_last_sum
# ---------------------------------------------------------------------------


class TestAsyncGetLastSum:
    @staticmethod
    def _mock_hass(recorder_result: dict) -> tuple[MagicMock, MagicMock]:
        hass = MagicMock()
        recorder_instance = MagicMock()
        recorder_instance.async_add_executor_job = AsyncMock(
            return_value=recorder_result
        )
        with patch(_GET_INSTANCE_PATH, return_value=recorder_instance):
            return hass, recorder_instance

    @pytest.mark.asyncio
    async def test_returns_last_sum(self):
        entries = [{"sum": 10.0}, {"sum": 20.0}, {"sum": 30.0}]
        hass, recorder = self._mock_hass({"dom:stat": entries})

        with patch(_GET_INSTANCE_PATH, return_value=recorder):
            result = await async_get_last_sum(hass, "dom:stat", _DAY_START)

        assert result == pytest.approx(30.0)

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_prior_stats(self):
        hass, recorder = self._mock_hass({})

        with patch(_GET_INSTANCE_PATH, return_value=recorder):
            result = await async_get_last_sum(hass, "dom:stat", _DAY_START)

        assert result == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_returns_zero_when_sum_is_none(self):
        hass, recorder = self._mock_hass({"dom:stat": [{"sum": None}]})

        with patch(_GET_INSTANCE_PATH, return_value=recorder):
            result = await async_get_last_sum(hass, "dom:stat", _DAY_START)

        assert result == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_query_window_uses_lookback_hours(self):
        hass = MagicMock()
        before_dt = datetime(2024, 3, 15, 0, 0, tzinfo=UTC)
        recorder_instance = MagicMock()
        # Invoke the lambda so statistics_during_period is actually called
        recorder_instance.async_add_executor_job = AsyncMock(
            side_effect=lambda fn: fn()
        )

        with (
            patch(_GET_INSTANCE_PATH, return_value=recorder_instance),
            patch(_SDP_PATH) as mock_sdp,
        ):
            mock_sdp.return_value = {}
            await async_get_last_sum(hass, "dom:stat", before_dt, lookback_hours=10)

        assert mock_sdp.call_args[0][1] == before_dt - timedelta(hours=10)
        assert mock_sdp.call_args[0][2] == before_dt

    @pytest.mark.asyncio
    async def test_default_lookback_is_25_hours(self):
        hass = MagicMock()
        before_dt = datetime(2024, 3, 15, 0, 0, tzinfo=UTC)
        recorder_instance = MagicMock()
        recorder_instance.async_add_executor_job = AsyncMock(
            side_effect=lambda fn: fn()
        )

        with (
            patch(_GET_INSTANCE_PATH, return_value=recorder_instance),
            patch(_SDP_PATH) as mock_sdp,
        ):
            mock_sdp.return_value = {}
            await async_get_last_sum(hass, "dom:stat", before_dt)

        assert mock_sdp.call_args[0][1] == before_dt - timedelta(hours=25)


# ---------------------------------------------------------------------------
# async_inject_day
# ---------------------------------------------------------------------------


class TestAsyncInjectDay:
    @pytest.mark.asyncio
    async def test_uses_provided_seed_sums(self):
        hass = MagicMock()
        stat = _make_stat("dom:a")
        entries = [Entry(0, 5.0)]
        seed_sums = {"dom:a": 100.0}

        with patch(_ADD_STAT_PATH):
            result = await async_inject_day(
                hass, [(stat, entries)], _DATE, _DAY_START, seed_sums
            )

        assert result["dom:a"] == pytest.approx(105.0)

    @pytest.mark.asyncio
    async def test_queries_db_when_seed_missing(self):
        hass = MagicMock()
        stat = _make_stat("dom:a")
        entries = [Entry(0, 3.0)]

        recorder_instance = MagicMock()
        recorder_instance.async_add_executor_job = AsyncMock(
            return_value={"dom:a": [{"sum": 50.0}]}
        )

        with (
            patch(_GET_INSTANCE_PATH, return_value=recorder_instance),
            patch(_ADD_STAT_PATH),
        ):
            result = await async_inject_day(
                hass, [(stat, entries)], _DATE, _DAY_START, None
            )

        assert result["dom:a"] == pytest.approx(53.0)

    @pytest.mark.asyncio
    async def test_multiple_stats_chained(self):
        hass = MagicMock()
        stat_a = _make_stat("dom:a")
        stat_b = _make_stat("dom:b")
        seed_sums = {"dom:a": 10.0, "dom:b": 20.0}

        with patch(_ADD_STAT_PATH):
            result = await async_inject_day(
                hass,
                [(stat_a, [Entry(0, 1.0)]), (stat_b, [Entry(0, 2.0)])],
                _DATE,
                _DAY_START,
                seed_sums,
            )

        assert result["dom:a"] == pytest.approx(11.0)
        assert result["dom:b"] == pytest.approx(22.0)

    @pytest.mark.asyncio
    async def test_empty_entries_still_returns_seed(self):
        """Empty entry list: stat is skipped but seed is preserved for chaining."""
        hass = MagicMock()
        stat = _make_stat("dom:a")
        seed_sums = {"dom:a": 42.0}

        with patch(_ADD_STAT_PATH) as mock_add:
            result = await async_inject_day(
                hass, [(stat, [])], _DATE, _DAY_START, seed_sums
            )

        mock_add.assert_not_called()
        assert result["dom:a"] == pytest.approx(42.0)

    @pytest.mark.asyncio
    async def test_partial_seed_sums_queries_db_for_missing(self):
        """Only stats absent from seed_sums should trigger a DB query."""
        hass = MagicMock()
        stat_a = _make_stat("dom:a")
        stat_b = _make_stat("dom:b")

        recorder_instance = MagicMock()
        # Only "dom:b" should be queried
        recorder_instance.async_add_executor_job = AsyncMock(
            return_value={"dom:b": [{"sum": 7.0}]}
        )

        with (
            patch(_GET_INSTANCE_PATH, return_value=recorder_instance),
            patch(_ADD_STAT_PATH),
        ):
            result = await async_inject_day(
                hass,
                [(stat_a, [Entry(0, 1.0)]), (stat_b, [Entry(0, 2.0)])],
                _DATE,
                _DAY_START,
                seed_sums={"dom:a": 5.0},  # dom:b absent → DB lookup
            )

        assert result["dom:a"] == pytest.approx(6.0)
        assert result["dom:b"] == pytest.approx(9.0)
        # DB was queried exactly once (for dom:b)
        assert recorder_instance.async_add_executor_job.call_count == 1
