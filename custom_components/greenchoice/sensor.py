import logging
from collections import namedtuple
from datetime import timedelta

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

from .api import GreenchoiceApi
from .const import DEFAULT_NAME, DOMAIN
from .hourly_statistics import async_import_hourly_statistics
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


class GreenchoiceDataUpdateCoordinator(DataUpdateCoordinator[SensorUpdate]):
    """Class to manage fetching data from the API."""

    def __init__(
        self, hass: HomeAssistant, api: GreenchoiceApi, config_entry: ConfigEntry
    ) -> None:
        """Initialize."""
        self.api = api
        self.config_entry = config_entry
        self._backfilled = False
        coordinator_name = config_entry.data.get(CONF_NAME, DEFAULT_NAME)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{slugify(coordinator_name)}",
            update_interval=timedelta(hours=6),
        )

    async def _async_update_data(self) -> SensorUpdate:
        """Update data via library."""
        try:
            async with self.api:
                data = await self.api.update()

                # Side-effect: import/backfill hourly consumption into recorder stats.
                # On the first run, _BACKFILL_DAYS of history is fetched; on subsequent
                # runs the last _RETRY_DAYS are retried to catch late-published data.
                try:
                    await async_import_hourly_statistics(
                        self.hass,
                        api=self.api,
                        entry=self.config_entry,
                        first_run=not self._backfilled,
                    )
                    self._backfilled = True
                except Exception as err:
                    _LOGGER.debug("Hourly statistics import failed: %s", err)

                return data
        except Exception as exception:
            _LOGGER.error("Failed to update data: %s", exception)
            raise UpdateFailed() from exception


class GreenchoiceSensor(CoordinatorEntity, SensorEntity):
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
