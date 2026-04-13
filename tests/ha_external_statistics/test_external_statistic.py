"""Tests for ha_external_statistic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch

import pytest

from custom_components.greenchoice.ha_external_statistics import (
    external_statistic as _ext_stat_mod,
)
from custom_components.greenchoice.ha_external_statistics.external_statistic import (
    ExternalStatistic,
)

_STAT_PATH = f"{_ext_stat_mod.__name__}.async_add_external_statistics"

# ---------------------------------------------------------------------------
# Minimal entry type used across all tests
# ---------------------------------------------------------------------------


@dataclass
class Entry:
    hour: int
    value: float
    avg: float = 0.0
    low: float = 0.0
    high: float = 0.0


_DATE = date(2024, 3, 15)


def _ts(entry: Entry, for_date: date) -> datetime:
    return datetime(
        for_date.year, for_date.month, for_date.day, entry.hour, 0, tzinfo=UTC
    )


def _make_stat(**kwargs) -> ExternalStatistic[Entry]:
    defaults = dict(
        statistic_id="test_domain:test_stat",
        name="Test Stat",
        source="test_domain",
        unit_of_measurement="kWh",
        unit_class="energy",
        period_start_fn=_ts,
        value_fn=lambda e: e.value,
    )
    defaults.update(kwargs)
    return ExternalStatistic(**defaults)


# ---------------------------------------------------------------------------
# metadata property
# ---------------------------------------------------------------------------


class TestMetadata:
    def test_fields(self):
        stat = _make_stat()
        meta = stat.metadata
        # StatisticMetaData is a TypedDict — use dict-style access
        assert meta["statistic_id"] == "test_domain:test_stat"
        assert meta["name"] == "Test Stat"
        assert meta["source"] == "test_domain"
        assert meta["unit_of_measurement"] == "kWh"
        assert meta["unit_class"] == "energy"
        assert meta["has_sum"] is True


# ---------------------------------------------------------------------------
# build_stat_data
# ---------------------------------------------------------------------------


class TestBuildStatData:
    def test_empty_entries(self):
        stat = _make_stat()
        data, end_sum = stat.build_stat_data([], _DATE, seed_sum=5.0)
        assert data == []
        assert end_sum == 5.0

    def test_sum_accumulates(self):
        stat = _make_stat()
        entries = [Entry(0, 1.0), Entry(1, 2.0), Entry(2, 3.0)]
        data, end_sum = stat.build_stat_data(entries, _DATE, seed_sum=10.0)

        assert len(data) == 3
        assert end_sum == pytest.approx(16.0)
        assert data[0]["sum"] == pytest.approx(11.0)
        assert data[1]["sum"] == pytest.approx(13.0)
        assert data[2]["sum"] == pytest.approx(16.0)

    def test_state_equals_value(self):
        stat = _make_stat()
        entries = [Entry(0, 4.5)]
        data, _ = stat.build_stat_data(entries, _DATE)
        assert data[0]["state"] == pytest.approx(4.5)

    def test_timestamps_use_period_start_fn(self):
        stat = _make_stat()
        entries = [Entry(6, 1.0), Entry(12, 2.0)]
        data, _ = stat.build_stat_data(entries, _DATE)
        assert data[0]["start"] == datetime(2024, 3, 15, 6, 0, tzinfo=UTC)
        assert data[1]["start"] == datetime(2024, 3, 15, 12, 0, tzinfo=UTC)

    def test_no_sum_when_has_sum_false(self):
        stat = _make_stat(has_sum=False)
        entries = [Entry(0, 1.0)]
        data, end_sum = stat.build_stat_data(entries, _DATE, seed_sum=99.0)
        assert "sum" not in data[0]
        assert end_sum == 99.0  # unchanged when has_sum=False

    def test_mean_fn_included(self):
        stat = _make_stat(mean_fn=lambda e: e.avg)
        entries = [Entry(0, 1.0, avg=0.5)]
        data, _ = stat.build_stat_data(entries, _DATE)
        assert data[0]["mean"] == pytest.approx(0.5)

    def test_min_max_fn_included(self):
        stat = _make_stat(min_fn=lambda e: e.low, max_fn=lambda e: e.high)
        entries = [Entry(0, 1.0, low=0.1, high=1.9)]
        data, _ = stat.build_stat_data(entries, _DATE)
        assert data[0]["min"] == pytest.approx(0.1)
        assert data[0]["max"] == pytest.approx(1.9)

    def test_negative_values(self):
        """Returned energy / compensation values are often negative."""
        stat = _make_stat()
        entries = [Entry(0, -1.0), Entry(1, -2.0)]
        data, end_sum = stat.build_stat_data(entries, _DATE, seed_sum=0.0)
        assert end_sum == pytest.approx(-3.0)
        assert data[1]["sum"] == pytest.approx(-3.0)

    def test_seed_sum_chaining(self):
        """End sum of day N becomes seed sum of day N+1."""
        stat = _make_stat()
        _, day1_end = stat.build_stat_data([Entry(0, 5.0)], _DATE, seed_sum=0.0)
        data, day2_end = stat.build_stat_data([Entry(0, 3.0)], _DATE, seed_sum=day1_end)
        assert day2_end == pytest.approx(8.0)
        assert data[0]["sum"] == pytest.approx(8.0)


# ---------------------------------------------------------------------------
# inject
# ---------------------------------------------------------------------------


class TestInject:
    def _hass(self):
        return MagicMock()

    def test_inject_calls_async_add_external_statistics(self):
        stat = _make_stat()
        hass = self._hass()
        entries = [Entry(0, 1.0), Entry(1, 2.0)]

        with patch(_STAT_PATH) as mock_add:
            end_sum = stat.inject(hass, entries, _DATE, seed_sum=0.0)

        mock_add.assert_called_once()
        call_args = mock_add.call_args
        assert call_args[0][0] is hass
        assert call_args[0][1]["statistic_id"] == "test_domain:test_stat"
        assert len(call_args[0][2]) == 2
        assert end_sum == pytest.approx(3.0)

    def test_inject_skips_empty_entries(self):
        stat = _make_stat()
        hass = self._hass()

        with patch(_STAT_PATH) as mock_add:
            end_sum = stat.inject(hass, [], _DATE, seed_sum=7.0)

        mock_add.assert_not_called()
        assert end_sum == pytest.approx(7.0)

    def test_inject_returns_end_sum(self):
        stat = _make_stat()
        hass = self._hass()
        entries = [Entry(0, 10.0)]

        with patch(_STAT_PATH):
            end_sum = stat.inject(hass, entries, _DATE, seed_sum=5.0)

        assert end_sum == pytest.approx(15.0)


# ---------------------------------------------------------------------------
# Equality behaviour
# ---------------------------------------------------------------------------


class TestEquality:
    def test_equal_instances(self):
        a = _make_stat()
        b = _make_stat()
        assert a == b

    def test_different_statistic_id(self):
        a = _make_stat(statistic_id="d:a")
        b = _make_stat(statistic_id="d:b")
        assert a != b
