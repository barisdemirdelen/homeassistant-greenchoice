import logging
import typing as t
from collections import namedtuple
from datetime import timedelta

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    CONF_PASSWORD,
    CONF_USERNAME,
    CURRENCY_EURO,
    UnitOfEnergy,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    create_issue,
)
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import Throttle, slugify

from . import CONF_AGREEMENT_ID, CONF_CUSTOMER_NUMBER
from .api import GreenchoiceApi
from .const import DEFAULT_NAME, DOMAIN
from .model import SensorUpdate

_LOGGER = logging.getLogger(__name__)

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=3600)
UPDATE_INTERVAL = timedelta(hours=1)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(
            CONF_CUSTOMER_NUMBER,
            description="Fill in if you would like to use a specific customer number",
            default=0,
        ): cv.positive_int,
        vol.Optional(
            CONF_AGREEMENT_ID,
            description="Fill in if you would like to use a specific agreement id",
            default=0,
        ): cv.positive_int,
    }
)


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

    sensors = [
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
                return await self.api.update()
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


# YAML platform setup (DEPRECATED)
def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: t.Optional[DiscoveryInfoType] = None,
) -> None:
    """Set up Greenchoice sensors from YAML configuration (DEPRECATED)."""

    # Create deprecation warning
    create_issue(
        hass,
        "greenchoice",
        "yaml_deprecation",
        is_fixable=False,
        severity=IssueSeverity.WARNING,
        translation_key="yaml_deprecation",
        translation_placeholders={
            "domain": "greenchoice",
            "integration_title": "Greenchoice",
        },
    )

    _LOGGER.warning(
        "YAML configuration for Greenchoice is deprecated and will be removed "
        "in the next version. Please migrate to the UI-based configuration "
        "by removing the YAML configuration and re-adding the integration via "
        "Settings > Devices & Services"
    )

    name: str = config.get(CONF_NAME)
    username: str = config.get(CONF_USERNAME)
    password: str = config.get(CONF_PASSWORD)
    customer_number: int | None = config.get(CONF_CUSTOMER_NUMBER) or None
    agreement_id: int | None = config.get(CONF_AGREEMENT_ID) or None

    _LOGGER.debug("Set up platform")
    greenchoice_api = GreenchoiceApi(
        username, password, customer_number=customer_number, agreement_id=agreement_id
    )

    throttled_api_update(greenchoice_api)

    sensors = [
        GreenchoiceYamlSensor(
            greenchoice_api,
            name,
            sensor_name,
        )
        for sensor_name in sensor_infos
    ]

    add_entities(sensors, True)


# Legacy yaml sensor (DEPRECATED)
@Throttle(MIN_TIME_BETWEEN_UPDATES)
def throttled_api_update(api) -> SensorUpdate:
    _LOGGER.debug("Throttled update called.")
    api_result = api.sync_update()
    _LOGGER.debug("Api result: %s", api_result)
    return api_result


# Legacy yaml sensor (DEPRECATED)
class GreenchoiceYamlSensor(SensorEntity):
    """Legacy sensor class for YAML configuration (DEPRECATED)."""

    def __init__(
        self,
        greenchoice_api: GreenchoiceApi,
        name: str,
        measurement_type: str,
    ):
        self._api = greenchoice_api
        self._measurement_type = measurement_type
        self._measurement_date = None
        self._measurement_date_key = (
            "electricity_reading_date"
            if "electricity" in self._measurement_type
            else "gas_reading_date"
        )

        sensor_info = sensor_infos[self._measurement_type]

        self._attr_unique_id = f"{slugify(name)}_{measurement_type}"
        self._attr_name = self._attr_unique_id
        self._attr_icon = f"mdi:{sensor_info.icon}"

        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_device_class = sensor_info.device_class
        self._attr_native_unit_of_measurement = sensor_info.unit

    def update(self):
        """Get the latest data from the Greenchoice API."""
        _LOGGER.debug("Updating %s", self.name)
        api_result = throttled_api_update(self._api) or self._api.result

        if (
            not api_result
            or not hasattr(api_result, self._measurement_type)
            or not hasattr(api_result, self._measurement_date_key)
        ):
            return

        self._attr_native_value = getattr(api_result, self._measurement_type)
        self._measurement_date = getattr(api_result, self._measurement_date_key)

    @property
    def measurement_type(self):
        return self._measurement_type

    @property
    def measurement_date(self):
        return self._measurement_date
