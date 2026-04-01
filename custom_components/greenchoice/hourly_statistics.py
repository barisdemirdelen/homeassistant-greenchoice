"""Import Greenchoice hourly consumption into Home Assistant recorder statistics."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_import_statistics,
    statistics_during_period,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .api import GreenchoiceApi
from .const import DOMAIN
from .model import Consumptions

_LOGGER = logging.getLogger(__name__)

_STORE_VERSION = 1
_SIGNAL_PREFIX = f"{DOMAIN}_hourly_statistics_updated"

# How many days back to scan the recorder for gaps on each import cycle.
_MAX_BACKFILL_DAYS = 7


def hourly_statistics_signal(entry_id: str) -> str:
    return f"{_SIGNAL_PREFIX}_{entry_id}"


def hourly_consumption_entity_id(config_name: str) -> str:
    return f"sensor.{slugify(config_name)}_electricity_consumption_hourly"


def hourly_feed_in_entity_id(config_name: str) -> str:
    return f"sensor.{slugify(config_name)}_electricity_feed_in_hourly"


def hourly_gas_entity_id(config_name: str) -> str:
    return f"sensor.{slugify(config_name)}_gas_consumption_hourly"


def get_hourly_store(hass: HomeAssistant, entry_id: str) -> Store[dict]:
    return Store[dict](hass, _STORE_VERSION, _store_key(entry_id))


@dataclass(frozen=True)
class HourlyImportResult:
    imported: bool
    date: date
    points: int


def _store_key(entry_id: str) -> str:
    return f"{DOMAIN}.hourly_statistics.{entry_id}"


def _as_utc_start(dt: datetime) -> datetime:
    """Convert an API datetime to an aware UTC datetime used by recorder statistics."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return dt_util.as_utc(dt)


def _build_electricity_metadata(
    entry: ConfigEntry, consumption_id: str, feed_in_id: str
) -> tuple[StatisticMetaData, StatisticMetaData]:
    """Return the electricity consumption and feed-in StatisticMetaData for *entry*."""
    common = dict(
        has_sum=True,
        mean_type=StatisticMeanType.NONE,
        source="recorder",
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        unit_class=None,
    )
    return (
        StatisticMetaData(
            **common,
            name=f"{entry.title} Electricity consumption (hourly)",
            statistic_id=consumption_id,
        ),
        StatisticMetaData(
            **common,
            name=f"{entry.title} Electricity feed-in (hourly)",
            statistic_id=feed_in_id,
        ),
    )


def _build_gas_metadata(entry: ConfigEntry, gas_id: str) -> StatisticMetaData:
    """Return the gas consumption StatisticMetaData for *entry*."""
    return StatisticMetaData(
        has_sum=True,
        mean_type=StatisticMeanType.NONE,
        name=f"{entry.title} Gas consumption (hourly)",
        source="recorder",
        statistic_id=gas_id,
        unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        unit_class=None,
    )


@dataclass
class _DayStats:
    electricity_consumption: list[StatisticData]
    electricity_feed_in: list[StatisticData]
    gas_consumption: list[StatisticData]
    points: int
    sum_electricity_consumption: float
    sum_electricity_feed_in: float
    sum_gas_consumption: float


def _build_day_stats(
    consumptions: Consumptions,
    sum_electricity_consumption: float,
    sum_electricity_feed_in: float,
    sum_gas_consumption: float,
) -> _DayStats:
    """Build StatisticData lists for one day of API consumption data.

    Iterates the hourly items, accumulates running sums for electricity and gas,
    and returns a _DayStats with the stats lists and updated sums.
    ``points`` is the number of hours that had any data (electricity or gas).
    The caller is responsible for checking that ``points > 0`` before importing.
    """
    stats_consumption: list[StatisticData] = []
    stats_feed_in: list[StatisticData] = []
    stats_gas: list[StatisticData] = []
    points = 0

    for item in sorted(consumptions.consumption_costs, key=lambda x: x.consumed_on):
        if not item.electricity and not item.gas:
            continue

        start_utc = _as_utc_start(item.consumed_on)

        if item.electricity:
            delivered = float(item.electricity.total_delivery_consumption or 0.0)
            fed_in = abs(float(item.electricity.total_feed_in_consumption or 0.0))
            sum_electricity_consumption += delivered
            sum_electricity_feed_in += fed_in
            stats_consumption.append(
                StatisticData(
                    start=start_utc, state=delivered, sum=sum_electricity_consumption
                )
            )
            stats_feed_in.append(
                StatisticData(
                    start=start_utc, state=fed_in, sum=sum_electricity_feed_in
                )
            )

        if item.gas:
            gas_delivered = float(item.gas.total_delivery_consumption or 0.0)
            sum_gas_consumption += gas_delivered
            stats_gas.append(
                StatisticData(
                    start=start_utc, state=gas_delivered, sum=sum_gas_consumption
                )
            )

        points += 1

    return _DayStats(
        electricity_consumption=stats_consumption,
        electricity_feed_in=stats_feed_in,
        gas_consumption=stats_gas,
        points=points,
        sum_electricity_consumption=sum_electricity_consumption,
        sum_electricity_feed_in=sum_electricity_feed_in,
        sum_gas_consumption=sum_gas_consumption,
    )


@dataclass
class _ImportLoopResult:
    total_points: int
    last_imported_day: date | None
    sum_electricity_consumption: float
    sum_electricity_feed_in: float
    sum_gas_consumption: float


async def _import_days(
    hass: HomeAssistant,
    *,
    api: GreenchoiceApi,
    entry: ConfigEntry,
    days: list[date],
    sum_electricity_consumption: float,
    sum_electricity_feed_in: float,
    sum_gas_consumption: float,
) -> _ImportLoopResult:
    """Fetch API data and import hourly statistics for each day in *days*.

    Builds StatisticData series with correctly chained cumulative sums starting
    from the supplied initial values, and writes them to the HA recorder.
    Returns the total points imported, the last successfully imported day, and
    the final cumulative sums (to be persisted by the caller).
    """
    config_name = entry.data.get(CONF_NAME) or entry.title or DOMAIN
    metadata_consumption, metadata_feed_in = _build_electricity_metadata(
        entry,
        hourly_consumption_entity_id(config_name),
        hourly_feed_in_entity_id(config_name),
    )
    metadata_gas = _build_gas_metadata(entry, hourly_gas_entity_id(config_name))

    total_points = 0
    last_imported_day: date | None = None

    for target_day in days:
        consumptions = await api.get_consumptions(interval="Hour", start=target_day)
        day_stats = _build_day_stats(
            consumptions,
            sum_electricity_consumption,
            sum_electricity_feed_in,
            sum_gas_consumption,
        )
        sum_electricity_consumption = day_stats.sum_electricity_consumption
        sum_electricity_feed_in = day_stats.sum_electricity_feed_in
        sum_gas_consumption = day_stats.sum_gas_consumption

        _LOGGER.debug("Found %d hourly points for %s", day_stats.points, target_day)
        if not day_stats.points:
            continue

        if day_stats.electricity_consumption:
            async_import_statistics(
                hass, metadata_consumption, day_stats.electricity_consumption
            )
            async_import_statistics(
                hass, metadata_feed_in, day_stats.electricity_feed_in
            )
        if day_stats.gas_consumption:
            async_import_statistics(hass, metadata_gas, day_stats.gas_consumption)

        total_points += day_stats.points
        last_imported_day = target_day

    return _ImportLoopResult(
        total_points=total_points,
        last_imported_day=last_imported_day,
        sum_electricity_consumption=sum_electricity_consumption,
        sum_electricity_feed_in=sum_electricity_feed_in,
        sum_gas_consumption=sum_gas_consumption,
    )


async def _get_days_with_data(
    hass: HomeAssistant,
    statistic_id: str,
    start_date: date,
    end_date: date,
) -> dict[date, float]:
    """Query the HA recorder and return {date: end_of_day_sum} for days that have
    hourly statistics in [start_date, end_date]. Days with no records are absent
    from the returned dict, which is how callers detect gaps.
    """

    tz = dt_util.DEFAULT_TIME_ZONE
    start_dt = dt_util.as_utc(datetime.combine(start_date, time.min).replace(tzinfo=tz))
    end_dt = dt_util.as_utc(
        datetime.combine(end_date + timedelta(days=1), time.min).replace(tzinfo=tz)
    )

    try:
        instance = get_instance(hass)
        raw = await instance.async_add_executor_job(
            statistics_during_period,
            hass,
            start_dt,
            end_dt,
            {statistic_id},
            "hour",
            None,
            {"sum"},
        )
    except Exception as err:
        _LOGGER.warning(
            "Failed to query existing statistics for %s: %s", statistic_id, err
        )
        return {}

    day_sums: dict[date, float] = {}
    for stat in raw.get(statistic_id, []):
        stat_start = stat["start"]
        stat_sum = stat["sum"]
        if stat_sum is None:
            continue
        # Newer HA recorder versions return start as a Unix timestamp (float).
        if isinstance(stat_start, (int, float)):
            stat_start = datetime.fromtimestamp(stat_start, tz=dt_util.UTC)
        local_date = dt_util.as_local(stat_start).date()
        if start_date <= local_date <= end_date:
            # Keep the highest sum seen for each day (= the last hour's cumulative value).
            if float(stat_sum) > day_sums.get(local_date, float("-inf")):
                day_sums[local_date] = float(stat_sum)

    return day_sums


async def async_import_yesterday_hourly_statistics(
    hass: HomeAssistant, *, api: GreenchoiceApi, entry: ConfigEntry
) -> HourlyImportResult | None:
    """Scan the last 7 days of recorder statistics for gaps and backfill them from the API.

    Idempotent: days that already have hourly records in the HA recorder are skipped,
    regardless of whether this function has run before. This means the integration
    self-heals after multi-day internet outages without any manual intervention.
    """

    if "recorder" not in hass.config.components:
        _LOGGER.debug("Recorder not loaded; skipping hourly statistics import")
        return None

    local_now = dt_util.now()
    local_today = local_now.date()
    yesterday = local_today - timedelta(days=1)
    scan_start = yesterday - timedelta(days=_MAX_BACKFILL_DAYS - 1)

    store = get_hourly_store(hass, entry.entry_id)
    stored = await store.async_load() or {}

    config_name = entry.data.get(CONF_NAME) or entry.title or DOMAIN
    consumption_id = hourly_consumption_entity_id(config_name)
    feed_in_id = hourly_feed_in_entity_id(config_name)
    gas_id = hourly_gas_entity_id(config_name)

    # Ask the recorder which days already have data so we can find the gaps.
    consumption_day_sums = await _get_days_with_data(
        hass, consumption_id, scan_start, yesterday
    )
    feed_in_day_sums = await _get_days_with_data(
        hass, feed_in_id, scan_start, yesterday
    )
    gas_day_sums = await _get_days_with_data(hass, gas_id, scan_start, yesterday)

    missing_days = [
        scan_start + timedelta(days=i)
        for i in range(_MAX_BACKFILL_DAYS)
        if (scan_start + timedelta(days=i)) not in consumption_day_sums
    ]

    # Yesterday's data may not be published yet; hold it back until 13:00.
    # Data for any day older than yesterday is already available at any hour.
    max_process_day = yesterday
    if local_now.hour < 13 and yesterday in missing_days:
        _LOGGER.debug(
            "Deferring yesterday (%s) until 13:00 (now: %02d:%02d)",
            yesterday,
            local_now.hour,
            local_now.minute,
        )
        missing_days.remove(yesterday)
        max_process_day = yesterday - timedelta(days=1)
        if not missing_days:
            # Nothing older to backfill right now; come back after 13:00.
            return None

    if not missing_days:
        _LOGGER.debug("No missing days found in the last %d days", _MAX_BACKFILL_DAYS)
        return HourlyImportResult(imported=False, date=yesterday, points=0)

    # Starting from the first gap, also re-import every day that already exists in
    # the recorder up to max_process_day. Their cumulative sums were computed from a
    # different baseline and would cause discontinuities in the Energy dashboard.
    first_gap = missing_days[0]
    days_to_process = [
        first_gap + timedelta(days=i)
        for i in range((max_process_day - first_gap).days + 1)
    ]

    _LOGGER.debug(
        "Gap detected at %s; processing %s through %s",
        first_gap.isoformat(),
        first_gap.isoformat(),
        max_process_day.isoformat(),
    )

    # Use the day immediately before the first gap as the cumulative-sum anchor.
    # That entry is already present in the recorder dicts we fetched for gap detection.
    day_before_gap = first_gap - timedelta(days=1)
    import_result = await _import_days(
        hass,
        api=api,
        entry=entry,
        days=days_to_process,
        sum_electricity_consumption=consumption_day_sums.get(
            day_before_gap, float(stored.get("last_sum_consumption") or 0.0)
        ),
        sum_electricity_feed_in=feed_in_day_sums.get(
            day_before_gap, float(stored.get("last_sum_feed_in") or 0.0)
        ),
        sum_gas_consumption=gas_day_sums.get(
            day_before_gap, float(stored.get("last_sum_gas") or 0.0)
        ),
    )

    if import_result.last_imported_day is None:
        return HourlyImportResult(imported=False, date=yesterday, points=0)

    # Persist the most recent end-of-day sums as a fallback for the next cycle in
    # case the recorder query returns nothing (e.g. recorder not yet warmed up).
    stored["last_sum_consumption"] = import_result.sum_electricity_consumption
    stored["last_sum_feed_in"] = import_result.sum_electricity_feed_in
    stored["last_sum_gas"] = import_result.sum_gas_consumption
    await store.async_save(stored)
    async_dispatcher_send(hass, hourly_statistics_signal(entry.entry_id))

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
    """Force-reimport hourly statistics from start_date up to yesterday.

    Fetches fresh data from the API for every day in the range and writes it to
    the recorder, overwriting whatever is already there. Cumulative sums are
    anchored to the recorder data that precedes start_date so the series remains
    monotonically correct. Returns the total number of data points imported.
    """
    local_now = dt_util.now()
    yesterday = local_now.date() - timedelta(days=1)

    if start_date > yesterday:
        raise ValueError(f"start_date {start_date} must not be today or in the future")

    config_name = entry.data.get(CONF_NAME) or entry.title or DOMAIN
    consumption_id = hourly_consumption_entity_id(config_name)
    feed_in_id = hourly_feed_in_entity_id(config_name)
    gas_id = hourly_gas_entity_id(config_name)

    # Look up the end-of-day sum from the day before start_date so the
    # re-imported series continues the existing cumulative total correctly.
    day_before = start_date - timedelta(days=1)
    pre_consumption = await _get_days_with_data(
        hass, consumption_id, day_before, day_before
    )
    pre_feed_in = await _get_days_with_data(hass, feed_in_id, day_before, day_before)
    pre_gas = await _get_days_with_data(hass, gas_id, day_before, day_before)
    sum_electricity_consumption = pre_consumption.get(day_before, 0.0)
    sum_electricity_feed_in = pre_feed_in.get(day_before, 0.0)
    sum_gas_consumption = pre_gas.get(day_before, 0.0)

    num_days = (yesterday - start_date).days + 1

    _LOGGER.info(
        "Force-reimporting %d day(s) of hourly statistics from %s for %s",
        num_days,
        start_date.isoformat(),
        entry.title,
    )

    import_result = await _import_days(
        hass,
        api=api,
        entry=entry,
        days=[start_date + timedelta(days=i) for i in range(num_days)],
        sum_electricity_consumption=sum_electricity_consumption,
        sum_electricity_feed_in=sum_electricity_feed_in,
        sum_gas_consumption=sum_gas_consumption,
    )

    _LOGGER.info(
        "Force-reimport complete: %d hourly data point(s) over %d day(s) for %s",
        import_result.total_points,
        num_days,
        entry.title,
    )

    if import_result.total_points > 0:
        store = get_hourly_store(hass, entry.entry_id)
        stored = await store.async_load() or {}
        stored["last_sum_consumption"] = import_result.sum_electricity_consumption
        stored["last_sum_feed_in"] = import_result.sum_electricity_feed_in
        stored["last_sum_gas"] = import_result.sum_gas_consumption
        await store.async_save(stored)
        async_dispatcher_send(hass, hourly_statistics_signal(entry.entry_id))

    return import_result.total_points
