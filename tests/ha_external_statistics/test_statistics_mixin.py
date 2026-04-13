"""Tests for StatisticsLoopMixin — generic, no dependency on any concrete coordinator."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Awaitable, cast
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
            return None

        mixin.process_day = AsyncMock(side_effect=_process)
        await mixin._async_process_day_range(
            [date(2026, 3, 25), date(2026, 3, 26), date(2026, 3, 27)]
        )

        assert date(2026, 3, 25) in processed
        assert date(2026, 3, 26) not in processed
        assert date(2026, 3, 27) in processed

    @pytest.mark.asyncio
    async def test_seed_reset_after_failure(self):
        """Seed sums must be reset to None for the day after a failure."""
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
        assert seeds_received[date(2026, 3, 27)] is None  # reset after 26 failed

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
            return None

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
        with _patch_today():
            with pytest.raises(RuntimeError, match="HTTP 500"):
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
    async def test_500_in_middle_skips_day_and_continues(self):
        """HTTP 500 on one reimport day must be skipped; others are still imported."""
        mixin = _FakeMixin()
        processed = []
        fail_day = date(2026, 3, 26)

        async def _process(day, seed):
            if day == fail_day:
                raise RuntimeError("HTTP 500")
            processed.append(day)
            return None

        mixin.process_day = AsyncMock(side_effect=_process)
        with _patch_today():
            await mixin.async_reimport_statistics(date(2026, 3, 25))  # must not raise

        assert fail_day not in processed
        assert date(2026, 3, 25) in processed
        assert date(2026, 3, 27) in processed
