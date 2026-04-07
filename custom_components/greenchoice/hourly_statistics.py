"""Import Greenchoice hourly consumption into Home Assistant recorder statistics."""

from __future__ import annotations

import logging
from collections import namedtuple
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    statistics_during_period,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, CURRENCY_EURO, UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .api import GreenchoiceApi
from .const import DOMAIN
from .model import Consumptions

_LOGGER = logging.getLogger(__name__)

# Days of history to fetch on the very first run (backfill).
_BACKFILL_DAYS = 7
# Days to re-fetch on every subsequent update (retry recent days for late-published data).
_RETRY_DAYS = 3

_StatisticSpec = namedtuple("_StatisticSpec", ["name_suffix", "unit", "unit_class"])
# Order matters: it determines the async_import_statistics call order relied on by tests.
_STATISTIC_SPECS: dict[str, _StatisticSpec] = {
    "electricity_consumption": _StatisticSpec(
        "Electricity consumption (hourly)", UnitOfEnergy.KILO_WATT_HOUR, "energy"
    ),
    "electricity_feed_in": _StatisticSpec(
        "Electricity feed-in (hourly)", UnitOfEnergy.KILO_WATT_HOUR, "energy"
    ),
    "electricity_consumption_cost": _StatisticSpec(
        "Electricity consumption cost (hourly)", CURRENCY_EURO, None
    ),
    "electricity_feed_in_compensation": _StatisticSpec(
        "Electricity feed-in compensation (hourly)", CURRENCY_EURO, None
    ),
    "gas_consumption": _StatisticSpec(
        "Gas consumption (hourly)", UnitOfVolume.CUBIC_METERS, "volume"
    ),
    "gas_consumption_cost": _StatisticSpec(
        "Gas consumption cost (hourly)", CURRENCY_EURO, None
    ),
}


@dataclass(frozen=True)
class HourlyImportResult:
    imported: bool
    date: date
    points: int


def _day_start_utc(day: date) -> datetime:
    """Return the UTC datetime for midnight of *day* in the local timezone."""
    tz = dt_util.DEFAULT_TIME_ZONE
    return dt_util.as_utc(datetime.combine(day, time.min).replace(tzinfo=tz))


def _as_utc_start(dt: datetime) -> datetime:
    """Convert an API datetime to an aware UTC datetime used by recorder statistics."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return dt_util.as_utc(dt)


def _build_all_metadata(
    entry: ConfigEntry, config_name: str
) -> dict[str, StatisticMetaData]:
    """Return a StatisticMetaData for every statistic kind, keyed by kind."""
    return {
        kind: StatisticMetaData(
            has_sum=True,
            mean_type=StatisticMeanType.NONE,
            source="greenchoice",
            name=f"{entry.title} {spec.name_suffix}",
            statistic_id=f"{DOMAIN}:{slugify(config_name)}_{kind}",
            unit_of_measurement=spec.unit,
            unit_class=spec.unit_class,
        )
        for kind, spec in _STATISTIC_SPECS.items()
    }


@dataclass
class _DayStats:
    """StatisticData lists and running sums for one day of API consumption data."""

    stats: dict[str, list[StatisticData]]
    sums: dict[str, float]
    points: int


def _build_hourly_stats(
    consumptions: Consumptions,
    seed_sums: dict[str, float],
) -> _DayStats:
    """Build StatisticData lists for one day of API consumption data.

    Iterates the hourly items, accumulates running sums for electricity and gas,
    and returns a _DayStats with per-kind stats lists, updated sums, and point count.
    ``points`` is the number of hours that had any data (electricity or gas).
    The caller is responsible for checking that ``points > 0`` before importing.
    """
    stats: dict[str, list[StatisticData]] = {kind: [] for kind in _STATISTIC_SPECS}
    sums = dict(seed_sums)
    points = 0

    for item in sorted(consumptions.consumption_costs, key=lambda x: x.consumed_on):
        if not item.electricity and not item.gas:
            continue

        start_utc = _as_utc_start(item.consumed_on)

        if item.electricity:
            elec_values: dict[str, float] = {
                "electricity_consumption": float(
                    item.electricity.total_delivery_consumption or 0.0
                ),
                "electricity_feed_in": -float(
                    item.electricity.total_feed_in_consumption or 0.0
                ),
                "electricity_consumption_cost": float(
                    item.electricity.total_delivery_costs or 0.0
                )
                + float(item.electricity.total_fixed_costs or 0.0),
                "electricity_feed_in_compensation": float(
                    item.electricity.total_feed_in_compensation or 0.0
                )
                + float(item.electricity.total_feed_in_costs or 0.0),
            }
            for kind, value in elec_values.items():
                sums[kind] += value
                stats[kind].append(
                    StatisticData(start=start_utc, state=value, sum=sums[kind])
                )

        if item.gas:
            gas_values: dict[str, float] = {
                "gas_consumption": float(item.gas.total_delivery_consumption or 0.0),
                "gas_consumption_cost": float(item.gas.total_delivery_costs or 0.0)
                + float(item.gas.total_fixed_costs or 0.0),
            }
            for kind, value in gas_values.items():
                sums[kind] += value
                stats[kind].append(
                    StatisticData(start=start_utc, state=value, sum=sums[kind])
                )

        points += 1

    return _DayStats(stats=stats, sums=sums, points=points)


@dataclass
class _ImportLoopResult:
    total_points: int
    last_imported_day: date | None


async def _get_sum_before(
    hass: HomeAssistant,
    statistic_id: str,
    before_dt: datetime,
) -> float:
    """Return the last recorded cumulative sum strictly before *before_dt*.

    Queries a 25-hour window to cover DST transition days (23/25 h days).
    Falls back to 0.0 if no prior statistics exist.
    """
    query_start = before_dt - timedelta(hours=25)
    try:
        result = await get_instance(hass).async_add_executor_job(
            statistics_during_period,
            hass,
            query_start,
            before_dt,
            {statistic_id},
            "hour",
            None,
            {"sum"},
        )
    except Exception as err:
        _LOGGER.warning("Failed to query statistics for %s: %s", statistic_id, err)
        return 0.0

    entries = result.get(statistic_id, [])
    if not entries:
        return 0.0
    last = entries[-1]
    raw_sum = last.get("sum") if isinstance(last, dict) else getattr(last, "sum", None)
    return float(raw_sum or 0.0)


async def _seed_sums_from_db(
    hass: HomeAssistant,
    metadata: dict[str, StatisticMetaData],
    day: date,
) -> dict[str, float]:
    """Query the recorder for the cumulative sum before *day* for each statistic kind."""
    day_start_utc = _day_start_utc(day)
    result: dict[str, float] = {}
    for kind in _STATISTIC_SPECS:
        result[kind] = await _get_sum_before(
            hass, metadata[kind]["statistic_id"], day_start_utc
        )
    return result


async def _process_day_range(
    hass: HomeAssistant,
    *,
    api: GreenchoiceApi,
    entry: ConfigEntry,
    days: list[date],
) -> _ImportLoopResult:
    """Fetch and import hourly statistics for each day in *days* (oldest first).

    Seeds cumulative sums lazily from the recorder before the first day (and after
    any empty day), then chains them forward across consecutive days without extra
    DB queries — the same pattern as scratch2.py's ``_async_process_day_range``.
    """
    config_name = entry.data.get(CONF_NAME) or entry.title or DOMAIN
    metadata = _build_all_metadata(entry, config_name)

    # None = "query the recorder before processing this day"
    seed_sums: dict[str, float] | None = None

    total_points = 0
    last_imported_day: date | None = None

    for day in days:
        consumptions = await api.get_consumptions(interval="Hour", start=day)

        # Lazy seed: only hit the DB at the start of a new run or after an empty day.
        if seed_sums is None:
            seed_sums = await _seed_sums_from_db(hass, metadata, day)

        day_stats = _build_hourly_stats(consumptions, seed_sums)

        if not day_stats.points:
            _LOGGER.debug(
                "No hourly data available for %s — will retry on next update", day
            )
            # Reset seed so the next day re-queries the recorder for a safe baseline.
            seed_sums = None
            continue

        # Chain seeds into the next day (avoids extra DB queries for consecutive days).
        seed_sums = day_stats.sums

        for kind, stat_list in day_stats.stats.items():
            if stat_list:
                stat_id = metadata[kind]["statistic_id"]
                try:
                    async_add_external_statistics(hass, metadata[kind], stat_list)
                except Exception as err:
                    raise RuntimeError(
                        f"async_add_external_statistics failed for statistic_id={stat_id!r}: {err}"
                    ) from err

        total_points += day_stats.points
        last_imported_day = day
        _LOGGER.debug("Imported %d hourly points for %s", day_stats.points, day)

    return _ImportLoopResult(
        total_points=total_points,
        last_imported_day=last_imported_day,
    )


async def async_import_hourly_statistics(
    hass: HomeAssistant,
    *,
    api: GreenchoiceApi,
    entry: ConfigEntry,
    first_run: bool,
) -> HourlyImportResult | None:
    """Import hourly statistics from Greenchoice into the HA recorder.

    On *first_run* (``True``): backfills the last ``_BACKFILL_DAYS`` days so the
    Energy Dashboard is populated right after installation.
    On subsequent calls (``False``): retries the last ``_RETRY_DAYS`` days to pick
    up data that was not yet published on the previous cycle.

    Yesterday is deferred until 13:00 as Greenchoice typically publishes the
    previous day's data in the morning.
    """
    if "recorder" not in hass.config.components:
        _LOGGER.debug("Recorder not loaded; skipping hourly statistics import")
        return None

    yesterday = dt_util.now().date() - timedelta(days=1)
    num_days = _BACKFILL_DAYS if first_run else _RETRY_DAYS

    # Build the day range oldest-first.
    days = [yesterday - timedelta(days=i) for i in range(num_days - 1, -1, -1)]

    import_result = await _process_day_range(hass, api=api, entry=entry, days=days)

    if import_result.last_imported_day is None:
        return HourlyImportResult(imported=False, date=yesterday, points=0)

    return HourlyImportResult(
        imported=True,
        date=import_result.last_imported_day,
        points=import_result.total_points,
    )


async def async_reimport_hourly_statistics_from(
    hass: HomeAssistant,
    *,
    api: GreenchoiceApi,
    entry: ConfigEntry,
    start_date: date,
) -> int:
    """Force-reimport hourly statistics from *start_date* up to yesterday.

    Fetches fresh data from the API for every day in the range and writes it to
    the recorder, overwriting whatever is already there. Cumulative sums are
    anchored to the recorder data that precedes *start_date* so the series
    remains monotonically correct. Returns the total number of data points imported.
    """
    local_now = dt_util.now()
    yesterday = local_now.date() - timedelta(days=1)

    if start_date > yesterday:
        raise ValueError(f"start_date {start_date} must not be today or in the future")

    num_days = (yesterday - start_date).days + 1
    days = [start_date + timedelta(days=i) for i in range(num_days)]

    _LOGGER.info(
        "Force-reimporting %d day(s) of hourly statistics from %s for %s",
        num_days,
        start_date.isoformat(),
        entry.title,
    )

    import_result = await _process_day_range(hass, api=api, entry=entry, days=days)

    _LOGGER.info(
        "Force-reimport complete: %d hourly data point(s) over %d day(s) for %s",
        import_result.total_points,
        num_days,
        entry.title,
    )

    return import_result.total_points
