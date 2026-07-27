import logging
from collections import namedtuple
from datetime import date, timedelta

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    CURRENCY_EURO,
    UnitOfEnergy,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import slugify

from custom_components.greenchoice.ha_external_statistics.recorder import (
    async_inject_day,
)
from custom_components.greenchoice.ha_external_statistics.statistics_mixin import (
    StatisticsLoopMixin,
)

from .api import ApiError, GreenchoiceApi
from .auth import LoginError
from .const import DEFAULT_NAME, DOMAIN
from .hourly_statistics import _day_start_utc, _make_statistics
from .model import SensorUpdate

_LOGGER = logging.getLogger(__name__)


class Unit:
    KWH = UnitOfEnergy.KILO_WATT_HOUR
    EUR_KWH = f"{CURRENCY_EURO}/{UnitOfEnergy.KILO_WATT_HOUR}"
    M3 = UnitOfVolume.CUBIC_METERS
    EUR_M3 = f"{CURRENCY_EURO}/{UnitOfVolume.CUBIC_METERS}"


SensorInfo = namedtuple("SensorInfo", ["device_class", "unit", "icon"])
sensor_infos = {
    "electricity_consumption_off_peak": SensorInfo(
        SensorDeviceClass.ENERGY, Unit.KWH, "weather-sunset-down"
    ),
    "electricity_consumption_normal": SensorInfo(
        SensorDeviceClass.ENERGY, Unit.KWH, "weather-sunset-up"
    ),
    "electricity_consumption_total": SensorInfo(
        SensorDeviceClass.ENERGY, Unit.KWH, "transmission-tower-export"
    ),
    "electricity_feed_in_off_peak": SensorInfo(
        SensorDeviceClass.ENERGY, Unit.KWH, "solar-power"
    ),
    "electricity_feed_in_normal": SensorInfo(
        SensorDeviceClass.ENERGY, Unit.KWH, "solar-power"
    ),
    "electricity_feed_in_total": SensorInfo(
        SensorDeviceClass.ENERGY, Unit.KWH, "transmission-tower-import"
    ),
    "electricity_price_single": SensorInfo(
        SensorDeviceClass.MONETARY, Unit.EUR_KWH, "currency-eur"
    ),
    "electricity_price_off_peak": SensorInfo(
        SensorDeviceClass.MONETARY, Unit.EUR_KWH, "currency-eur"
    ),
    "electricity_price_normal": SensorInfo(
        SensorDeviceClass.MONETARY, Unit.EUR_KWH, "currency-eur"
    ),
    "electricity_feed_in_compensation": SensorInfo(
        SensorDeviceClass.MONETARY, Unit.EUR_KWH, "currency-eur"
    ),
    "electricity_feed_in_cost": SensorInfo(
        SensorDeviceClass.MONETARY, Unit.EUR_KWH, "currency-eur"
    ),
    "gas_consumption": SensorInfo(SensorDeviceClass.GAS, Unit.M3, "fire"),
    "gas_price": SensorInfo(SensorDeviceClass.MONETARY, Unit.EUR_M3, "currency-eur"),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Greenchoice sensors from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    sensors: list[SensorEntity] = [
        GreenchoiceSensor(coordinator, sensor_name) for sensor_name in sensor_infos
    ]
    async_add_entities(sensors)


class GreenchoiceDataUpdateCoordinator(
    StatisticsLoopMixin, DataUpdateCoordinator[SensorUpdate]
):
    """Class to manage fetching data from the API."""

    config_entry: ConfigEntry

    def __init__(
        self, hass: HomeAssistant, api: GreenchoiceApi, config_entry: ConfigEntry
    ) -> None:
        """Initialize."""
        self.api = api
        coordinator_name = config_entry.data.get(CONF_NAME, DEFAULT_NAME)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{slugify(coordinator_name)}",
            update_interval=timedelta(hours=6),
            backfill_days=7,
            retry_days=3,
        )
        # Set after super().__init__ so DataUpdateCoordinator's own
        # self.config_entry = None assignment doesn't overwrite ours.
        self.config_entry = config_entry

    async def _async_update_data(self) -> SensorUpdate:
        """Update data via library."""
        try:
            async with self.api:
                data = await self.api.update()

                # Side-effect: import/backfill hourly consumption into recorder stats.
                if "recorder" in self.hass.config.components:
                    try:
                        await self.async_run_statistics_update()
                    except Exception as err:
                        _LOGGER.debug(
                            "Hourly statistics import failed: %s", err, exc_info=True
                        )

                return data
        except (ApiError, LoginError) as exception:
            # Expected upstream failures: let the coordinator log them concisely
            # and retry. Anything else propagates so Home Assistant logs a full
            # traceback instead of an empty "Failed to update data".
            raise UpdateFailed(
                str(exception) or type(exception).__name__
            ) from exception

    async def _process_day(
        self,
        day: date,
        seed_sums: dict[str, float] | None,
    ) -> dict[str, float] | None:
        """Fetch and inject hourly statistics for *day*.

        Returns statistic_id-keyed seed sums for the next consecutive day,
        or ``None`` if no data was available yet.
        Called from within an open ``async with self.api:`` context.
        """
        config_name = (
            self.config_entry.data.get(CONF_NAME) or self.config_entry.title
        ) or DOMAIN
        electricity_stats, gas_stats = _make_statistics(self.config_entry, config_name)

        consumptions = await self.api.get_consumptions(interval="Hour", start=day)
        items = sorted(consumptions.consumption_costs, key=lambda x: x.consumed_on)
        electricity_items = [item for item in items if item.electricity]
        gas_items = [item for item in items if item.gas]

        if not electricity_items and not gas_items:
            _LOGGER.debug("No hourly data for %s — will retry on next update", day)
            return None

        stats_entries = [
            *((stat, electricity_items) for stat in electricity_stats),
            *((stat, gas_items) for stat in gas_stats),
        ]
        # Drop stats whose item list is empty (e.g. no gas on electricity-only day).
        stats_entries = [(stat, entries) for stat, entries in stats_entries if entries]

        day_start = _day_start_utc(day)
        new_sums = await async_inject_day(
            self.hass, stats_entries, day, day_start, seed_sums
        )
        _LOGGER.debug("Imported hourly data for %s", day)
        return new_sums

    async def async_force_reimport(self, start_date: date) -> None:
        """Open the API session and reimport statistics from *start_date*."""
        async with self.api:
            await self.async_reimport_statistics(start_date)


class GreenchoiceSensor(
    CoordinatorEntity[GreenchoiceDataUpdateCoordinator], SensorEntity
):
    """Representation of a Greenchoice sensor for async config flow."""

    def __init__(
        self,
        coordinator: GreenchoiceDataUpdateCoordinator,
        measurement_type: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._measurement_type = measurement_type
        self._measurement_date_key = (
            "electricity_reading_date"
            if "electricity" in self._measurement_type
            else "gas_reading_date"
        )

        sensor_info = sensor_infos[self._measurement_type]

        # Get human-readable name from config entry
        sensor_title = coordinator.config_entry.data.get(CONF_NAME, DEFAULT_NAME)

        # Use sensor_title as prefix instead of DOMAIN
        self._attr_unique_id = f"{slugify(sensor_title)}_{measurement_type}"
        self._attr_name = f"{sensor_title} {measurement_type.replace('_', ' ').title()}"
        self._attr_icon = f"mdi:{sensor_info.icon}"
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_device_class = sensor_info.device_class
        self._attr_native_unit_of_measurement = sensor_info.unit

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None

        if not hasattr(self.coordinator.data, self._measurement_type):
            return None

        return getattr(self.coordinator.data, self._measurement_type)

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.data:
            return None

        if not hasattr(self.coordinator.data, self._measurement_date_key):
            return None

        return {
            "measurement_date": getattr(
                self.coordinator.data, self._measurement_date_key
            )
        }
