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
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import slugify

from . import CONF_AGREEMENT_ID, CONF_CUSTOMER_NUMBER
from .api import GreenchoiceApi
from .const import DEFAULT_NAME, DOMAIN
from .hourly_statistics import (
    async_import_yesterday_hourly_statistics,
    get_hourly_store,
    hourly_consumption_entity_id,
    hourly_feed_in_entity_id,
    hourly_gas_entity_id,
    hourly_statistics_signal,
)
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
    sensors.extend(
        [
            GreenchoiceHourlyEnergySensor(hass, entry, kind="electricity_consumption"),
            GreenchoiceHourlyEnergySensor(hass, entry, kind="electricity_feed_in"),
            GreenchoiceHourlyEnergySensor(hass, entry, kind="gas_consumption"),
        ]
    )

    async_add_entities(sensors)


class GreenchoiceDataUpdateCoordinator(DataUpdateCoordinator[SensorUpdate]):
    """Class to manage fetching data from the API."""

    def __init__(
        self, hass: HomeAssistant, api: GreenchoiceApi, config_entry: ConfigEntry
    ) -> None:
        """Initialize."""
        self.api = api
        self.config_entry = config_entry
        coordinator_name = config_entry.data.get(CONF_NAME, DEFAULT_NAME)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{slugify(coordinator_name)}",
            update_interval=timedelta(minutes=60),
        )

    async def _async_update_data(self) -> SensorUpdate:
        """Update data via library."""
        try:
            async with self.api:
                data = await self.api.update()

                # Side-effect: backfill yesterday's hourly consumption into recorder stats.
                # This is idempotent and safe to run on each refresh.
                try:
                    await async_import_yesterday_hourly_statistics(
                        self.hass, api=self.api, entry=self.config_entry
                    )
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


class GreenchoiceHourlyEnergySensor(SensorEntity):
    """Energy dashboard compatible sensor for imported hourly statistics.

    This entity exists mainly so the Energy dashboard UI can select it; the actual
    hourly data is imported into recorder statistics.
    """

    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, *, kind: str) -> None:
        self._hass = hass
        self._entry = entry
        self._kind = kind

        config_name = entry.data.get(CONF_NAME, DEFAULT_NAME)
        prefix = slugify(config_name)

        if kind == "electricity_consumption":
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
            self._attr_name = f"{config_name} Electricity consumption (hourly)"
            self._attr_unique_id = f"{prefix}_electricity_consumption_hourly"
            self._attr_icon = "mdi:transmission-tower-export"
            self.entity_id = hourly_consumption_entity_id(config_name)
        elif kind == "electricity_feed_in":
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
            self._attr_name = f"{config_name} Electricity feed-in (hourly)"
            self._attr_unique_id = f"{prefix}_electricity_feed_in_hourly"
            self._attr_icon = "mdi:transmission-tower-import"
            self.entity_id = hourly_feed_in_entity_id(config_name)
        elif kind == "gas_consumption":
            self._attr_device_class = SensorDeviceClass.GAS
            self._attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
            self._attr_name = f"{config_name} Gas consumption (hourly)"
            self._attr_unique_id = f"{prefix}_gas_consumption_hourly"
            self._attr_icon = "mdi:fire"
            self.entity_id = hourly_gas_entity_id(config_name)
        else:
            raise ValueError(f"Unknown kind: {kind}")

        self._store: Store[dict] = get_hourly_store(hass, entry.entry_id)
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self._async_refresh_from_store()

        signal = hourly_statistics_signal(self._entry.entry_id)
        self.async_on_remove(
            async_dispatcher_connect(self._hass, signal, self._async_handle_signal)
        )

    async def _async_handle_signal(self) -> None:
        await self._async_refresh_from_store()
        self.async_write_ha_state()

    async def _async_refresh_from_store(self) -> None:
        stored = await self._store.async_load() or {}
        store_key = {
            "electricity_consumption": "last_sum_consumption",
            "electricity_feed_in": "last_sum_feed_in",
            "gas_consumption": "last_sum_gas",
        }[self._kind]
        self._attr_native_value = stored.get(store_key) or 0.0
        self._attr_extra_state_attributes = {
            "last_imported": stored.get("last_imported"),
        }
