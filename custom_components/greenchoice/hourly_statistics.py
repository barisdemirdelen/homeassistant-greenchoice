"""Import Greenchoice hourly consumption into Home Assistant recorder statistics."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from homeassistant.const import CONF_NAME, UnitOfEnergy
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import slugify
from homeassistant.util import dt as dt_util

from .api import GreenchoiceApi
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_STORE_VERSION = 1

_SIGNAL_PREFIX = f"{DOMAIN}_hourly_statistics_updated"


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


async def async_import_yesterday_hourly_statistics(
    hass: HomeAssistant, *, api: GreenchoiceApi, entry: ConfigEntry
) -> HourlyImportResult | None:
    """Fetch yesterday's hourly consumptions and import them into recorder statistics.

    Idempotent: stores the last imported date + last cumulative sums in storage and
    will skip importing the same date again.
    """

    # If recorder isn't loaded/enabled, importing will fail anyway.
    if "recorder" not in hass.config.components:
        _LOGGER.debug("Recorder not loaded; skipping hourly statistics import")
        return None

    store: Store[dict] = get_hourly_store(hass, entry.entry_id)
    stored = await store.async_load() or {}

    local_now = dt_util.now()
    local_today = local_now.date()
    target_day = local_today - timedelta(days=1)

    if stored.get("last_imported") == target_day.isoformat():
        return HourlyImportResult(imported=False, date=target_day, points=0)

    # Delay import until 12:00 to give Greenchoice time to process data.
    if local_now.hour < 13:
        _LOGGER.debug(
            "Skipping hourly statistics import before 13:00 (now: %02d:%02d)",
            local_now.hour,
            local_now.minute,
        )
        return None

    # Ensure we have identifiers resolved for the hourly endpoint.
    if not api.customer_number or not api.agreement_id:
        prefs = await api.get_preferences()
        api.customer_number = prefs.customer_number
        api.agreement_id = prefs.agreement_id

    consumptions = await api.get_consumptions(
        interval="Hour", start=target_day, end=target_day + timedelta(days=1)
    )

    # Import consumption (delivery) and feed-in as separate increasing series.
    try:
        from homeassistant.components.recorder.models import (
            StatisticData,
            StatisticMeanType,
            StatisticMetaData,
        )
        from homeassistant.components.recorder.statistics import async_import_statistics
    except Exception as err:  # pragma: no cover
        _LOGGER.warning("Recorder statistics import unavailable: %s", err)
        return None

    last_sum_consumption = float(stored.get("last_sum_consumption") or 0.0)
    last_sum_feed_in = float(stored.get("last_sum_feed_in") or 0.0)

    stats_consumption: list[StatisticData] = []
    stats_feed_in: list[StatisticData] = []

    points = 0
    for item in sorted(consumptions.consumption_costs, key=lambda x: x.consumed_on):
        if not item.electricity:
            continue

        start = _as_utc_start(item.consumed_on)

        delivered = float(item.electricity.total_delivery_consumption or 0.0)
        feed_in_raw = float(item.electricity.total_feed_in_consumption or 0.0)
        fed_in = abs(feed_in_raw)

        last_sum_consumption += delivered
        last_sum_feed_in += fed_in

        stats_consumption.append(
            StatisticData(start=start, state=delivered, sum=last_sum_consumption)
        )
        stats_feed_in.append(
            StatisticData(start=start, state=fed_in, sum=last_sum_feed_in)
        )
        points += 1

    _LOGGER.debug("Found %d hourly consumption points for %s", points, target_day)

    if not points:
        return HourlyImportResult(imported=False, date=target_day, points=0)

    config_name = _config_name(entry)

    metadata_consumption = StatisticMetaData(
        has_sum=True,
        mean_type=StatisticMeanType.NONE,
        name=f"{entry.title} Electricity consumption (hourly)",
        source="recorder",
        statistic_id=hourly_consumption_entity_id(config_name),
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    )
    metadata_feed_in = StatisticMetaData(
        has_sum=True,
        mean_type=StatisticMeanType.NONE,
        name=f"{entry.title} Electricity feed-in (hourly)",
        source="recorder",
        statistic_id=hourly_feed_in_entity_id(config_name),
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    )

    async_import_statistics(hass, metadata_consumption, stats_consumption)
    async_import_statistics(hass, metadata_feed_in, stats_feed_in)

    stored["last_imported"] = target_day.isoformat()
    stored["last_sum_consumption"] = last_sum_consumption
    stored["last_sum_feed_in"] = last_sum_feed_in
    await store.async_save(stored)
    async_dispatcher_send(hass, hourly_statistics_signal(entry.entry_id))

    return HourlyImportResult(imported=True, date=target_day, points=points)
