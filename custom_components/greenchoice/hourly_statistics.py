"""Greenchoice ExternalStatistic definitions for hourly recorder statistics."""

from __future__ import annotations

from datetime import date, datetime, time

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CURRENCY_EURO, UnitOfEnergy, UnitOfVolume
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from custom_components.greenchoice.ha_external_statistics.external_statistic import (
    ExternalStatistic,
)

from .const import DOMAIN
from .model import ConsumptionCostsItem


def _day_start_utc(day: date) -> datetime:
    """Return the UTC datetime for midnight of *day* in the local timezone."""
    tz = dt_util.DEFAULT_TIME_ZONE
    return dt_util.as_utc(datetime.combine(day, time.min).replace(tzinfo=tz))


def _as_utc_start(dt: datetime) -> datetime:
    """Convert an API datetime to an aware UTC datetime used by recorder statistics."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return dt_util.as_utc(dt)


def _make_statistics(
    entry: ConfigEntry,
    config_name: str,
) -> tuple[
    list[ExternalStatistic[ConsumptionCostsItem]],
    list[ExternalStatistic[ConsumptionCostsItem]],
]:
    """Return ``(electricity_stats, gas_stats)`` ExternalStatistic lists.

    Each statistic's *period_start_fn* derives the UTC timestamp from
    ``item.consumed_on``; *value_fn* extracts the relevant field.
    The electricity and gas lists are kept separate so the caller can
    filter items before pairing them up.
    """

    def _stat(kind, name_suffix, unit, unit_class, value_fn):
        return ExternalStatistic(
            statistic_id=f"{DOMAIN}:{slugify(config_name)}_{kind}",
            name=f"{entry.title} {name_suffix}",
            source=DOMAIN,
            unit_of_measurement=unit,
            unit_class=unit_class,
            period_start_fn=lambda item, _d: _as_utc_start(item.consumed_on),
            value_fn=value_fn,
        )

    electricity_stats = [
        _stat(
            "electricity_consumption",
            "Electricity consumption (hourly)",
            UnitOfEnergy.KILO_WATT_HOUR,
            "energy",
            lambda item: float(item.electricity.total_delivery_consumption or 0.0),
        ),
        _stat(
            "electricity_feed_in",
            "Electricity feed-in (hourly)",
            UnitOfEnergy.KILO_WATT_HOUR,
            "energy",
            lambda item: -float(item.electricity.total_feed_in_consumption or 0.0),
        ),
        _stat(
            "electricity_consumption_cost",
            "Electricity consumption cost (hourly)",
            CURRENCY_EURO,
            None,
            lambda item: float(item.electricity.total_delivery_costs or 0.0)
            + float(item.electricity.total_fixed_costs or 0.0),
        ),
        _stat(
            "electricity_feed_in_compensation",
            "Electricity feed-in compensation (hourly)",
            CURRENCY_EURO,
            None,
            lambda item: -(
                float(item.electricity.total_feed_in_compensation or 0.0)
                + float(item.electricity.total_feed_in_costs or 0.0)
            ),
        ),
    ]

    gas_stats = [
        _stat(
            "gas_consumption",
            "Gas consumption (hourly)",
            UnitOfVolume.CUBIC_METERS,
            "volume",
            lambda item: float(item.gas.total_delivery_consumption or 0.0),
        ),
        _stat(
            "gas_consumption_cost",
            "Gas consumption cost (hourly)",
            CURRENCY_EURO,
            None,
            lambda item: float(item.gas.total_delivery_costs or 0.0)
            + float(item.gas.total_fixed_costs or 0.0),
        ),
    ]

    return electricity_stats, gas_stats
