"""
base_coordinator.py

Pure mixin that manages backfill, retry-recent, and reimport scheduling.

Mix this alongside ``DataUpdateCoordinator`` and implement ``_process_day``
to fetch and inject one calendar day's statistics.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import date, timedelta

from homeassistant.helpers.update_coordinator import UpdateFailed

_LOGGER = logging.getLogger(__name__)


class StatisticsLoopMixin(ABC):
    """
    Mixin that owns the backfill / retry / reimport control flow.

    Does NOT inherit from ``DataUpdateCoordinator`` — mix it alongside one.
    The MRO must place this mixin *before* ``DataUpdateCoordinator`` so that
    ``__init__`` correctly consumes *backfill_days* / *retry_days* before
    forwarding remaining kwargs to the coordinator.

    Subclasses must implement:

    * ``_process_day`` — fetch + inject one calendar day's statistics.
    """

    def __init__(self, *args, backfill_days: int, retry_days: int, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._backfill_days = backfill_days
        self._retry_days = retry_days
        self._stats_backfilled = False

    @staticmethod
    def _today() -> date:
        """Return today's date. Exists as a method so tests can override it."""
        return date.today()

    # ── Abstract interface ───────────────────────────────────────────────────

    @abstractmethod
    async def _process_day(
        self,
        day: date,
        seed_sums: dict[str, float] | None,
    ) -> dict[str, float] | None:
        """
        Fetch and inject statistics for *day*.

        Return a seed-sums dict on success — it is passed unchanged to the
        next consecutive day's call, avoiding redundant DB queries.
        Return ``None`` when the API has no data yet for this day (pending /
        empty) — the next day will re-query the DB for its own seed.
        Raise on unrecoverable errors.
        """

    # ── Entry point ──────────────────────────────────────────────────────────

    async def async_run_statistics_update(self) -> None:
        """
        Run one statistics update cycle.

        On the first call: backfill ``_backfill_days`` days of history.
        On subsequent calls: retry the last ``_retry_days`` days to pick up
        late-published data.

        Raises ``UpdateFailed`` on unhandled errors.
        """
        try:
            if not self._stats_backfilled:
                await self._async_backfill(self._backfill_days)
                self._stats_backfilled = True
            else:
                await self._async_retry_recent_days(self._retry_days)
        except UpdateFailed:
            raise
        except Exception as err:
            raise UpdateFailed(f"Error fetching energy statistics: {err}") from err

    # ── Core loop ────────────────────────────────────────────────────────────

    async def _async_process_day_range(
        self,
        days: list[date],
        *,
        raise_if_all_fail: bool = False,
    ) -> None:
        """
        Iterate *days* (oldest first), calling ``_process_day`` for each.

        Seed sums are chained across consecutive successful days.  When
        ``_process_day`` returns ``None`` (empty day) or raises, the seed is
        reset so the next day re-queries the DB for a safe baseline.

        When *raise_if_all_fail* is ``True`` and every attempt raised an
        exception, the last exception is re-raised.
        """
        seed_sums: dict[str, float] | None = None
        any_success = False
        last_exc: Exception | None = None

        for day in days:
            try:
                seed_sums = await self._process_day(day, seed_sums)
                any_success = True
                # None return → empty day; seed stays None → next day hits DB.
            except Exception as exc:
                _LOGGER.warning(
                    "Failed to fetch data for %s, skipping.", day, exc_info=True
                )
                seed_sums = None
                last_exc = exc

        if raise_if_all_fail and not any_success and last_exc is not None:
            raise last_exc

    # ── Scheduling helpers ───────────────────────────────────────────────────

    async def _async_retry_recent_days(self, days: int) -> None:
        """Re-process the last *days* calendar days, raising if all fail."""
        today = self._today()
        day_range = [today - timedelta(days=offset) for offset in range(days, 0, -1)]
        await self._async_process_day_range(day_range, raise_if_all_fail=True)

    async def _async_backfill(self, days: int) -> None:
        """Process the last *days* calendar days, silently skipping failures."""
        today = self._today()
        day_range = [today - timedelta(days=offset) for offset in range(days, 0, -1)]
        await self._async_process_day_range(day_range)

    async def async_reimport_statistics(self, start_date: date) -> None:
        """Reimport all statistics from *start_date* through yesterday (inclusive)."""
        yesterday = self._today() - timedelta(days=1)
        if start_date > yesterday:
            _LOGGER.warning(
                "Reimport start_date %s is not before today — nothing to do.",
                start_date,
            )
            return

        total_days = (yesterday - start_date).days + 1
        _LOGGER.info(
            "Starting statistics reimport from %s to %s (%d days).",
            start_date,
            yesterday,
            total_days,
        )

        day_range = [start_date + timedelta(days=i) for i in range(total_days)]
        await self._async_process_day_range(day_range)

        _LOGGER.info("Statistics reimport complete.")
