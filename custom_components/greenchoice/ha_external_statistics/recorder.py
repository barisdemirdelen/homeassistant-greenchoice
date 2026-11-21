"""
recorder.py

Async helpers that talk to the HA recorder on behalf of
``ExternalStatistic`` instances.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import (
    statistic_during_period,
)
from homeassistant.core import HomeAssistant

from .external_statistic import ExternalStatistic


async def async_get_last_sum(
    hass: HomeAssistant,
    stat_id: str,
    before_dt: datetime,
) -> float:
    """
    Return the last recorded cumulative sum for *stat_id* strictly before
    *before_dt*.

    Searches all prior history, including gaps between imports.
    Returns ``0.0`` when no prior statistics exist.

    Parameters
    ----------
    hass:
        The Home Assistant instance.
    stat_id:
        Fully-qualified statistic ID, e.g. ``"my_domain:electricity_consumed"``.
    before_dt:
        Upper bound (exclusive) for the query — typically the UTC start of the
        day you are about to inject.
    """
    # Keep partial-hour bounds on hourly statistics rather than HA's short-term table.
    query_end = before_dt.replace(minute=0, second=0, microsecond=0)
    if query_end < before_dt:
        query_end += timedelta(hours=1)

    # With no start, HA computes change from zero using the latest prior sum.
    result = await get_instance(hass).async_add_executor_job(
        lambda: statistic_during_period(
            hass,
            None,
            query_end,
            stat_id,
            {"change"},
            None,
        ),
    )
    return float(result.get("change") or 0.0)


async def async_inject_day(
    hass: HomeAssistant,
    stats_entries: Iterable[tuple[ExternalStatistic[Any], list[Any]]],
    for_date: date,
    day_start_utc: datetime,
    seed_sums: dict[str, float] | None = None,
) -> dict[str, float]:
    """
    Inject one day of statistics for multiple ``ExternalStatistic`` instances.

    For each ``(stat, entries)`` pair:

    * If *seed_sums* already contains a value for ``stat.statistic_id``, that
      value is used as the running-sum seed — no DB query is made.
    * Otherwise the seed is fetched from the recorder via
      :func:`async_get_last_sum`.

    Returns a ``{statistic_id: end_sum}`` mapping that can be passed directly
    as *seed_sums* for the **next** consecutive day, avoiding redundant DB
    queries when back-filling a range of days.

    When *seed_sums* is ``None`` every statistic performs a DB lookup.
    Pass an empty dict ``{}`` to get the same effect as ``None``.

    Parameters
    ----------
    hass:
        The Home Assistant instance.
    stats_entries:
        An iterable of ``(ExternalStatistic, entries)`` pairs.  Each pair is
        processed in iteration order; entries may be an empty list (the stat
        is skipped but its seed sum is still captured for chaining).
    for_date:
        The calendar date being injected.  Passed through to
        ``ExternalStatistic.inject()``.
    day_start_utc:
        UTC ``datetime`` for midnight of *for_date* in the integration's local
        timezone.  Used as the ``before_dt`` for seed-sum DB queries.
    seed_sums:
        Running sums carried over from the previous day, keyed by
        ``statistic_id``.  Pass ``None`` (or omit) to query the DB for every
        statistic.
    """
    result_sums: dict[str, float] = {}

    for stat, entries in stats_entries:
        if seed_sums is not None and stat.statistic_id in seed_sums:
            seed = seed_sums[stat.statistic_id]
        else:
            seed = await async_get_last_sum(hass, stat.statistic_id, day_start_utc)

        result_sums[stat.statistic_id] = stat.inject(hass, entries, for_date, seed)

    return result_sums
