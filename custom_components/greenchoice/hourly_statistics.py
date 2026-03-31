"""Import Greenchoice hourly consumption into Home Assistant recorder statistics."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, UnitOfEnergy
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


def get_hourly_store(hass: HomeAssistant, entry_id: str) -> Store[dict]:
    return Store(hass, _STORE_VERSION, _store_key(entry_id))


@dataclass(frozen=True)
class HourlyImportResult:
    imported: bool
    date: date
    points: int


def _store_key(entry_id: str) -> str:
    return f"{DOMAIN}.hourly_statistics.{entry_id}"


def _config_name(entry: ConfigEntry) -> str:
    return entry.data.get(CONF_NAME) or entry.title or DOMAIN


def _as_utc_start(dt: datetime) -> datetime:
    """Convert an API datetime to an aware UTC datetime used by recorder statistics."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return dt_util.as_utc(dt)


def _build_day_stats(
    consumptions: Consumptions,
    sum_consumption: float,
    sum_feed_in: float,
) -> tuple[list, list, int, float, float]:
    """Build StatisticData lists for one day of API consumption data.

    Iterates the hourly consumption items, accumulates running sums, and returns
    ``(stats_consumption, stats_feed_in, points, sum_consumption, sum_feed_in)``.
    The caller is responsible for checking that ``points > 0`` before importing.
    This is the single source of truth for how raw API data becomes recorder stats.
    """

    stats_consumption: list = []
    stats_feed_in: list = []
    points = 0

    for item in sorted(consumptions.consumption_costs, key=lambda x: x.consumed_on):
        if not item.electricity:
            continue

        start_utc = _as_utc_start(item.consumed_on)
        delivered = float(item.electricity.total_delivery_consumption or 0.0)
        fed_in = abs(float(item.electricity.total_feed_in_consumption or 0.0))

        sum_consumption += delivered
        sum_feed_in += fed_in

        stats_consumption.append(
            StatisticData(start=start_utc, state=delivered, sum=sum_consumption)
        )
        stats_feed_in.append(
            StatisticData(start=start_utc, state=fed_in, sum=sum_feed_in)
        )
        points += 1

    return stats_consumption, stats_feed_in, points, sum_consumption, sum_feed_in


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
    try:
        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder.statistics import (
            statistics_during_period,
        )
    except Exception:
        return {}

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
        stat_start = stat["start"] if isinstance(stat, dict) else stat.start
        stat_sum = stat["sum"] if isinstance(stat, dict) else stat.sum
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

    config_name = _config_name(entry)
    consumption_id = hourly_consumption_entity_id(config_name)
    feed_in_id = hourly_feed_in_entity_id(config_name)

    # Ask the recorder which days already have data so we can find the gaps.
    consumption_day_sums = await _get_days_with_data(
        hass, consumption_id, scan_start, yesterday
    )
    feed_in_day_sums = await _get_days_with_data(
        hass, feed_in_id, scan_start, yesterday
    )

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

    if not api.customer_number or not api.agreement_id:
        prefs = await api.get_preferences()
        api.customer_number = prefs.customer_number
        api.agreement_id = prefs.agreement_id

    metadata_consumption = StatisticMetaData(
        has_sum=True,
        mean_type=StatisticMeanType.NONE,
        name=f"{entry.title} Electricity consumption (hourly)",
        source="recorder",
        statistic_id=consumption_id,
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        unit_class=None,
    )
    metadata_feed_in = StatisticMetaData(
        has_sum=True,
        mean_type=StatisticMeanType.NONE,
        name=f"{entry.title} Electricity feed-in (hourly)",
        source="recorder",
        statistic_id=feed_in_id,
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        unit_class=None,
    )

    total_points = 0
    last_imported_day: date | None = None

    for target_day in days_to_process:
        # Determine starting sums from the most recent prior day that has recorder data.
        # Days we successfully imported earlier in this same loop are also included
        # because we add them to consumption_day_sums below.
        prior_days = sorted(d for d in consumption_day_sums if d < target_day)
        if prior_days:
            sum_consumption = consumption_day_sums[prior_days[-1]]
            sum_feed_in = feed_in_day_sums.get(prior_days[-1], 0.0)
        else:
            # No recorder data found before this day; fall back to persisted sums.
            sum_consumption = float(stored.get("last_sum_consumption") or 0.0)
            sum_feed_in = float(stored.get("last_sum_feed_in") or 0.0)

        consumptions = await api.get_consumptions(interval="Hour", start=target_day)

        stats_consumption, stats_feed_in, points, sum_consumption, sum_feed_in = (
            _build_day_stats(consumptions, sum_consumption, sum_feed_in)
        )

        _LOGGER.debug("Found %d hourly points for %s", points, target_day)

        if not points:
            # API has no data for this day yet; skip without persisting so we retry.
            continue

        async_import_statistics(hass, metadata_consumption, stats_consumption)
        async_import_statistics(hass, metadata_feed_in, stats_feed_in)

        # Register this day's end sums so subsequent iterations in this loop can
        # build correct cumulative sums on top of them.
        consumption_day_sums[target_day] = sum_consumption
        feed_in_day_sums[target_day] = sum_feed_in

        total_points += points
        last_imported_day = target_day

    if last_imported_day is None:
        return HourlyImportResult(imported=False, date=yesterday, points=0)

    # Persist the most recent end-of-day sums as a fallback for the next cycle in
    # case the recorder query returns nothing (e.g. recorder not yet warmed up).
    stored["last_sum_consumption"] = consumption_day_sums[last_imported_day]
    stored["last_sum_feed_in"] = feed_in_day_sums[last_imported_day]
    await store.async_save(stored)
    async_dispatcher_send(hass, hourly_statistics_signal(entry.entry_id))

    return HourlyImportResult(
        imported=True, date=last_imported_day, points=total_points
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

    if not api.customer_number or not api.agreement_id:
        prefs = await api.get_preferences()
        api.customer_number = prefs.customer_number
        api.agreement_id = prefs.agreement_id

    config_name = _config_name(entry)
    consumption_id = hourly_consumption_entity_id(config_name)
    feed_in_id = hourly_feed_in_entity_id(config_name)

    # Look up the end-of-day sum from the day before start_date so the
    # re-imported series continues the existing cumulative total correctly.
    day_before = start_date - timedelta(days=1)
    pre_consumption = await _get_days_with_data(
        hass, consumption_id, day_before, day_before
    )
    pre_feed_in = await _get_days_with_data(hass, feed_in_id, day_before, day_before)
    sum_consumption = pre_consumption.get(day_before, 0.0)
    sum_feed_in = pre_feed_in.get(day_before, 0.0)

    metadata_consumption = StatisticMetaData(
        has_sum=True,
        mean_type=StatisticMeanType.NONE,
        name=f"{entry.title} Electricity consumption (hourly)",
        source="recorder",
        statistic_id=consumption_id,
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        unit_class=None,
    )
    metadata_feed_in = StatisticMetaData(
        has_sum=True,
        mean_type=StatisticMeanType.NONE,
        name=f"{entry.title} Electricity feed-in (hourly)",
        source="recorder",
        statistic_id=feed_in_id,
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        unit_class=None,
    )

    num_days = (yesterday - start_date).days + 1
    total_points = 0

    _LOGGER.info(
        "Force-reimporting %d day(s) of hourly statistics from %s for %s",
        num_days,
        start_date.isoformat(),
        entry.title,
    )

    for i in range(num_days):
        target_day = start_date + timedelta(days=i)
        consumptions = await api.get_consumptions(interval="Hour", start=target_day)

        stats_consumption, stats_feed_in, points, sum_consumption, sum_feed_in = (
            _build_day_stats(consumptions, sum_consumption, sum_feed_in)
        )

        if not points:
            _LOGGER.debug("No API data for %s, skipping", target_day)
            continue

        async_import_statistics(hass, metadata_consumption, stats_consumption)
        async_import_statistics(hass, metadata_feed_in, stats_feed_in)
        total_points += points
        _LOGGER.debug("Reimported %d hourly points for %s", points, target_day)

    if total_points > 0:
        store = get_hourly_store(hass, entry.entry_id)
        stored = await store.async_load() or {}
        stored["last_sum_consumption"] = sum_consumption
        stored["last_sum_feed_in"] = sum_feed_in
        await store.async_save(stored)
        async_dispatcher_send(hass, hourly_statistics_signal(entry.entry_id))

    _LOGGER.info(
        "Force-reimport complete: %d hourly data point(s) over %d day(s) for %s",
        total_points,
        num_days,
        entry.title,
    )
    return total_points
