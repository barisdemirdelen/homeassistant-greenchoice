"""Tests for StatisticsLoopMixin — generic, no dependency on any concrete coordinator."""

from __future__ import annotations

from collections.abc import Awaitable
from datetime import date, timedelta
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.greenchoice.ha_external_statistics.statistics_mixin import (
    StatisticsLoopMixin,
)

# ---------------------------------------------------------------------------
# Minimal concrete implementation
# ---------------------------------------------------------------------------

_TODAY = date(2026, 3, 28)
_YESTERDAY = _TODAY - timedelta(days=1)


class _FakeMixin(StatisticsLoopMixin):
    """Concrete subclass that delegates _process_day to a replaceable AsyncMock."""

    process_day: AsyncMock

    def __init__(self, backfill_days: int = 7, retry_days: int = 3):
        super().__init__(backfill_days=backfill_days, retry_days=retry_days)
        self.process_day = AsyncMock(return_value=None)

    async def _process_day(
        self,
        day: date,
        seed_sums: dict[str, float] | None,
    ) -> dict[str, float] | None:
        return await cast(Awaitable, self.process_day(day, seed_sums))


def _patch_today(today: date = _TODAY):
    return patch.object(StatisticsLoopMixin, "_today", return_value=today)


# ---------------------------------------------------------------------------
# _async_process_day_range
# ---------------------------------------------------------------------------


class TestProcessDayRange:
    @pytest.mark.asyncio
    async def test_calls_process_day_for_each_day(self):
        mixin = _FakeMixin()
        days = [date(2026, 3, 25), date(2026, 3, 26), date(2026, 3, 27)]
        await mixin._async_process_day_range(days)
        assert mixin.process_day.call_count == 3

    @pytest.mark.asyncio
    async def test_skips_failing_day_and_continues(self):
        """A day that raises (e.g. HTTP 500) must be skipped; later days still run."""
        mixin = _FakeMixin()
        processed = []

        async def _process(day, seed):
            if day == date(2026, 3, 26):
                raise RuntimeError("HTTP 500")
            processed.append(day)

        mixin.process_day = AsyncMock(side_effect=_process)
        await mixin._async_process_day_range(
            [date(2026, 3, 25), date(2026, 3, 26), date(2026, 3, 27)]
        )

        assert date(2026, 3, 25) in processed
        assert date(2026, 3, 26) not in processed
        assert date(2026, 3, 27) in processed

    @pytest.mark.asyncio
    async def test_seed_preserved_after_failure(self):
        """Seed sums must be preserved after a failure (failed day = zero consumption).

        Resetting the seed to None causes the next day to re-query the DB with a
        stale baseline, which produces a large negative spike in the statistics graph.
        Instead the last-successful seed should be forwarded unchanged so the
        cumulative sum continues from the correct value.
        """
        mixin = _FakeMixin()
        seeds_received: dict[date, object] = {}

        async def _process(day, seed):
            seeds_received[day] = seed
            if day == date(2026, 3, 26):
                raise RuntimeError("HTTP 500")
            return {"stat": 1.0}

        mixin.process_day = AsyncMock(side_effect=_process)
        await mixin._async_process_day_range(
            [date(2026, 3, 25), date(2026, 3, 26), date(2026, 3, 27)]
        )

        assert seeds_received[date(2026, 3, 25)] is None  # no prior seed
        assert seeds_received[date(2026, 3, 26)] == {"stat": 1.0}  # chained from 25
        # Seed must be preserved (not reset) so the next day's cumulative sum
        # continues from the same baseline instead of producing a negative spike.
        assert seeds_received[date(2026, 3, 27)] == {"stat": 1.0}

    @pytest.mark.asyncio
    async def test_seeds_chained_across_consecutive_successes(self):
        mixin = _FakeMixin()
        seeds_received: dict[date, object] = {}

        async def _process(day, seed):
            seeds_received[day] = seed
            return {"stat": float(day.day)}

        mixin.process_day = AsyncMock(side_effect=_process)
        await mixin._async_process_day_range(
            [date(2026, 3, 25), date(2026, 3, 26), date(2026, 3, 27)]
        )

        assert seeds_received[date(2026, 3, 25)] is None
        assert seeds_received[date(2026, 3, 26)] == {"stat": 25.0}
        assert seeds_received[date(2026, 3, 27)] == {"stat": 26.0}

    @pytest.mark.asyncio
    async def test_raise_if_all_fail_reraises_when_every_day_fails(self):
        mixin = _FakeMixin()
        mixin.process_day = AsyncMock(side_effect=RuntimeError("HTTP 500"))

        with pytest.raises(RuntimeError, match="HTTP 500"):
            await mixin._async_process_day_range(
                [date(2026, 3, 26), date(2026, 3, 27)],
                raise_if_all_fail=True,
            )

    @pytest.mark.asyncio
    async def test_raise_if_all_fail_silent_when_at_least_one_succeeds(self):
        mixin = _FakeMixin()
        # First day fails, second day succeeds.
        mixin.process_day = AsyncMock(side_effect=[RuntimeError("HTTP 500"), None])

        # Must not raise.
        await mixin._async_process_day_range(
            [date(2026, 3, 26), date(2026, 3, 27)],
            raise_if_all_fail=True,
        )

    @pytest.mark.asyncio
    async def test_empty_day_list_is_a_no_op(self):
        mixin = _FakeMixin()
        await mixin._async_process_day_range([])
        mixin.process_day.assert_not_called()


# ---------------------------------------------------------------------------
# _async_backfill
# ---------------------------------------------------------------------------


class TestBackfill:
    @pytest.mark.asyncio
    async def test_processes_n_days_before_today(self):
        mixin = _FakeMixin(backfill_days=3)
        with _patch_today():
            await mixin._async_backfill(3)

        days = [c.args[0] for c in mixin.process_day.call_args_list]
        assert days == [
            _TODAY - timedelta(days=3),
            _TODAY - timedelta(days=2),
            _YESTERDAY,
        ]

    @pytest.mark.asyncio
    async def test_500_in_middle_skips_day_and_continues(self):
        """HTTP 500 on one backfill day is skipped; the rest are still imported."""
        mixin = _FakeMixin(backfill_days=3)
        processed = []
        fail_day = _TODAY - timedelta(days=2)

        async def _process(day, seed):
            if day == fail_day:
                raise RuntimeError("HTTP 500")
            processed.append(day)

        mixin.process_day = AsyncMock(side_effect=_process)
        with _patch_today():
            await mixin._async_backfill(3)  # must not raise

        assert fail_day not in processed
        assert len(processed) == 2

    @pytest.mark.asyncio
    async def test_all_days_fail_does_not_raise(self):
        """Backfill swallows all errors silently — it is best-effort."""
        mixin = _FakeMixin(backfill_days=3)
        mixin.process_day = AsyncMock(side_effect=RuntimeError("HTTP 500"))
        with _patch_today():
            await mixin._async_backfill(3)  # must not raise


# ---------------------------------------------------------------------------
# _async_retry_recent_days
# ---------------------------------------------------------------------------


class TestRetryRecentDays:
    @pytest.mark.asyncio
    async def test_processes_n_days_before_today(self):
        mixin = _FakeMixin(retry_days=2)
        with _patch_today():
            await mixin._async_retry_recent_days(2)

        days = [c.args[0] for c in mixin.process_day.call_args_list]
        assert days == [_TODAY - timedelta(days=2), _YESTERDAY]

    @pytest.mark.asyncio
    async def test_500_on_one_day_does_not_raise_if_another_succeeds(self):
        mixin = _FakeMixin(retry_days=2)
        # First call raises, second succeeds.
        mixin.process_day = AsyncMock(side_effect=[RuntimeError("HTTP 500"), None])
        with _patch_today():
            await mixin._async_retry_recent_days(2)  # must not raise

    @pytest.mark.asyncio
    async def test_all_days_fail_raises(self):
        """If every retry day fails, the last exception must propagate."""
        mixin = _FakeMixin(retry_days=2)
        mixin.process_day = AsyncMock(side_effect=RuntimeError("HTTP 500"))
        with _patch_today(), pytest.raises(RuntimeError, match="HTTP 500"):
            await mixin._async_retry_recent_days(2)


# ---------------------------------------------------------------------------
# async_run_statistics_update
# ---------------------------------------------------------------------------


class TestRunStatisticsUpdate:
    @pytest.mark.asyncio
    async def test_first_call_runs_backfill_and_sets_flag(self):
        mixin = _FakeMixin(backfill_days=2)
        assert mixin._stats_backfilled is False
        with _patch_today():
            await mixin.async_run_statistics_update()
        assert mixin._stats_backfilled is True
        assert mixin.process_day.call_count == 2

    @pytest.mark.asyncio
    async def test_second_call_runs_retry(self):
        mixin = _FakeMixin(backfill_days=7, retry_days=2)
        mixin._stats_backfilled = True
        with _patch_today():
            await mixin.async_run_statistics_update()
        assert mixin.process_day.call_count == 2

    @pytest.mark.asyncio
    async def test_500_during_backfill_does_not_raise_and_sets_flag(self):
        """Backfill errors must not surface — the flag is still set."""
        mixin = _FakeMixin(backfill_days=3)
        mixin.process_day = AsyncMock(side_effect=RuntimeError("HTTP 500"))
        with _patch_today():
            await mixin.async_run_statistics_update()  # must not raise
        assert mixin._stats_backfilled is True


# ---------------------------------------------------------------------------
# async_reimport_statistics
# ---------------------------------------------------------------------------


class TestReimportStatistics:
    @pytest.mark.asyncio
    async def test_covers_start_through_yesterday(self):
        mixin = _FakeMixin()
        start = date(2026, 3, 25)
        with _patch_today():
            await mixin.async_reimport_statistics(start)

        days = [c.args[0] for c in mixin.process_day.call_args_list]
        assert days[0] == start
        assert days[-1] == _YESTERDAY
        assert len(days) == (_YESTERDAY - start).days + 1

    @pytest.mark.asyncio
    async def test_today_or_future_is_a_no_op(self):
        mixin = _FakeMixin()
        with _patch_today():
            await mixin.async_reimport_statistics(_TODAY)
        mixin.process_day.assert_not_called()

    @pytest.mark.asyncio
    async def test_partial_reimport_after_full_reimport_is_safe(self):
        """Full reimport 1st–30th, then partial reimport 15th–30th → all values correct.

        The first day of every reimport range always starts with seed_sums=None.
        In production code this triggers a DB lookup (async_get_last_sum) that
        returns the correct end-of-day-14 baseline, so the cumulative sums for
        days 15–30 are recalculated correctly.  Days 1–14 are never touched.

        This test confirms the exact seeds received by each call so the contract
        is explicit and regression-proof.
        """
        # today = March 31 → yesterday = March 30, so the range covers all 30 days.
        _MARCH_31 = date(2026, 3, 31)
        START = date(2026, 3, 1)  # first day of full reimport
        MID = date(2026, 3, 15)  # first day of partial reimport

        # Each day returns sum = day-of-month * 10.0  (e.g. March 14 → 140.0).
        def _end_sum(day: date) -> dict[str, float]:
            return {"stat": float((day - START).days + 1) * 10.0}

        # ── First reimport: 1st → 30th ──────────────────────────────────────
        seeds_first: dict[date, object] = {}

        async def _process_first(day, seed):
            seeds_first[day] = seed
            return _end_sum(day)

        mixin = _FakeMixin()
        mixin.process_day = AsyncMock(side_effect=_process_first)
        with _patch_today(_MARCH_31):
            await mixin.async_reimport_statistics(START)

        # Spot-check seed chaining in the first reimport.
        assert seeds_first[START] is None  # first day → DB lookup
        assert seeds_first[date(2026, 3, 2)] == {"stat": 10.0}  # chained from Mar 1
        assert seeds_first[date(2026, 3, 15)] == {"stat": 140.0}  # chained from Mar 14
        assert seeds_first[date(2026, 3, 30)] == {"stat": 290.0}  # chained from Mar 29

        # ── Second reimport: 15th → 30th ────────────────────────────────────
        seeds_second: dict[date, object] = {}

        async def _process_second(day, seed):
            seeds_second[day] = seed
            return _end_sum(day)

        mixin.process_day = AsyncMock(side_effect=_process_second)
        with _patch_today(_MARCH_31):
            await mixin.async_reimport_statistics(MID)

        # Day 15 is the first day of the partial reimport → seed must be None.
        # In real code this causes async_get_last_sum to read the correct
        # end-of-day-14 value (140.0) from the DB, so the sums stay correct.
        assert seeds_second[MID] is None  # DB lookup triggered
        # Days 16–30 chain directly from the previous day's return value.
        assert seeds_second[date(2026, 3, 16)] == {"stat": 150.0}  # chained from Mar 15
        assert seeds_second[date(2026, 3, 30)] == {"stat": 290.0}  # chained from Mar 29
        # Days 1–14 were never called in the second reimport.
        assert START not in seeds_second
        assert date(2026, 3, 14) not in seeds_second

    @pytest.mark.asyncio
    async def test_500_in_middle_skips_day_and_continues(self):
        """HTTP 500 on one reimport day must be skipped; others are still imported."""
        mixin = _FakeMixin()
        processed = []
        fail_day = date(2026, 3, 26)

        async def _process(day, seed):
            if day == fail_day:
                raise RuntimeError("HTTP 500")
            processed.append(day)

        mixin.process_day = AsyncMock(side_effect=_process)
        with _patch_today():
            await mixin.async_reimport_statistics(date(2026, 3, 25))  # must not raise

        assert fail_day not in processed
        assert date(2026, 3, 25) in processed
        assert date(2026, 3, 27) in processed
