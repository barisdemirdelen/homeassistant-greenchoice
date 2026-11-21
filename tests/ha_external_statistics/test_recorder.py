"""Tests for ha_external_statistic.recorder helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.recorder.statistics import (
    StatisticData,
    async_add_external_statistics,
    statistics_during_period,
)
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

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
        hass, recorder = self._mock_hass({"change": 30.0})

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
        hass, recorder = self._mock_hass({"change": None})

        with patch(_GET_INSTANCE_PATH, return_value=recorder):
            result = await async_get_last_sum(hass, "dom:stat", _DAY_START)

        assert result == pytest.approx(0.0)


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
            return_value={"change": 50.0}
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
            return_value={"change": 7.0}
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


@pytest.mark.usefixtures("recorder_mock")
@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        ([(-720, 100.0), (-168, 120.0)], 120.0),
        ([(-1, 40.0)], 40.0),
        ([], 0.0),
        ([(-720, 100.0), (-168, 0.0)], 0.0),
        ([(-168, -20.0)], -20.0),
        ([(-1, 40.0), (0, 900.0), (1, 1000.0)], 40.0),
        ([(0, 900.0), (1, 1000.0)], 0.0),
    ],
    ids=[
        "long-gap",
        "adjacent",
        "empty",
        "zero",
        "negative",
        "exclusive-bound",
        "future-only",
    ],
)
async def test_seed_from_recorded_history(hass, rows, expected):
    """The latest sum strictly before the import survives any gap."""
    stat = _make_stat()
    if rows:
        async_add_external_statistics(
            hass,
            stat.metadata,
            [
                StatisticData(start=_DAY_START + timedelta(hours=hours), sum=value)
                for hours, value in rows
            ],
        )
        await async_wait_recording_done(hass)

    assert await async_get_last_sum(hass, stat.statistic_id, _DAY_START) == expected


@pytest.mark.usefixtures("recorder_mock")
async def test_historical_reimports_do_not_double_count(hass):
    """Reimported hours use their predecessor, even with later data present."""
    stat = _make_stat()
    async_add_external_statistics(
        hass,
        stat.metadata,
        [
            StatisticData(start=_DAY_START - timedelta(days=30), sum=100.0),
            StatisticData(start=_DAY_START + timedelta(days=2), sum=900.0),
        ],
    )
    await async_wait_recording_done(hass)

    for _ in range(2):
        sums = await async_inject_day(
            hass, [(stat, [Entry(0, 2.0), Entry(1, 3.0)])], _DATE, _DAY_START
        )
        assert sums == {stat.statistic_id: 105.0}
        await async_wait_recording_done(hass)
        sums = await async_inject_day(
            hass,
            [(stat, [Entry(0, 4.0)])],
            _DATE + timedelta(days=1),
            _DAY_START + timedelta(days=1),
            sums,
        )
        assert sums == {stat.statistic_id: 109.0}
        await async_wait_recording_done(hass)

    recorded = await hass.async_add_executor_job(
        statistics_during_period,
        hass,
        _DAY_START,
        _DAY_START + timedelta(days=3),
        {stat.statistic_id},
        "hour",
        None,
        {"sum"},
    )
    assert [row["sum"] for row in recorded[stat.statistic_id]] == [
        102.0,
        105.0,
        109.0,
        900.0,
    ]


@pytest.mark.usefixtures("recorder_mock")
@pytest.mark.parametrize(
    "offset",
    [timedelta(minutes=30), timedelta(seconds=1), timedelta(microseconds=1)],
)
async def test_seed_before_partial_hour_boundary(hass, offset):
    """An hourly row starting before the boundary must still be included."""
    stat = _make_stat()
    async_add_external_statistics(
        hass,
        stat.metadata,
        [
            StatisticData(start=_DAY_START - timedelta(hours=1), sum=30.0),
            StatisticData(start=_DAY_START, sum=40.0),
            StatisticData(start=_DAY_START + timedelta(hours=1), sum=50.0),
        ],
    )
    await async_wait_recording_done(hass)

    assert (
        await async_get_last_sum(hass, stat.statistic_id, _DAY_START + offset) == 40.0
    )
