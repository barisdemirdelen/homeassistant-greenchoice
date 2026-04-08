"""
recorder.py

Async helpers that talk to the HA recorder on behalf of
``ExternalStatistic`` instances.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Iterable

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import (
    statistics_during_period,
)
from homeassistant.core import HomeAssistant

from .external_statistic import ExternalStatistic


async def async_get_last_sum(
    hass: HomeAssistant,
    stat_id: str,
    before_dt: datetime,
    *,
    lookback_hours: int = 25,
) -> float:
    """
    Return the last recorded cumulative sum for *stat_id* strictly before
    *before_dt*.

    A *lookback_hours* window (default **25 h**) is used so that DST
    transition days (which can be 23 or 25 hours long) are always covered.
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
    lookback_hours:
        How far back to search for an existing sum.  25 hours covers every
        real-world DST transition.
    """
    query_start = before_dt - timedelta(hours=lookback_hours)
    result = await get_instance(hass).async_add_executor_job(
        lambda: statistics_during_period(
            hass,
            query_start,
            before_dt,
            {stat_id},
            "hour",
            None,
            {"sum"},
        ),
    )
    entries = result.get(stat_id, [])
    if entries:
        last = entries[-1]
        raw_sum = last.get("sum") if isinstance(last, dict) else getattr(last, "sum", None)
        return float(raw_sum or 0.0)
    return 0.0


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

