import logging
import typing as t
from collections import namedtuple
from datetime import timedelta

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
    PLATFORM_SCHEMA,
)
from homeassistant.const import CONF_NAME, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util import slugify, Throttle

from .api import GreenchoiceApiData

_LOGGER = logging.getLogger(__name__)

CONF_OVEREENKOMST_ID = "overeenkomst_id"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

DEFAULT_NAME = "Energieverbruik"
DEFAULT_DATE_FORMAT = "%y-%m-%dT%H:%M:%S"

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=3600)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_USERNAME, default=CONF_USERNAME): cv.string,
        vol.Optional(CONF_PASSWORD, default=CONF_USERNAME): cv.string,
        vol.Optional(CONF_OVEREENKOMST_ID, default=CONF_OVEREENKOMST_ID): cv.string,
    }
)


class Unit:
    kwh = "kWh"
    eur_kwh = "EUR/kWh"
    m3 = "m³"
    eur_m3 = "EUR/m³"


SensorInfo = namedtuple("SensorInfo", ["device_class", "unit", "icon"])
sensor_infos = {
    "electricity_consumption_high": SensorInfo(
        SensorDeviceClass.ENERGY, Unit.kwh, "weather-sunset-up"
    ),
    "electricity_consumption_low": SensorInfo(
        SensorDeviceClass.ENERGY, Unit.kwh, "weather-sunset-down"
    ),
    "electricity_consumption_total": SensorInfo(
        SensorDeviceClass.ENERGY, Unit.kwh, "transmission-tower-export"
    ),
    "electricity_return_high": SensorInfo(
        SensorDeviceClass.ENERGY, Unit.kwh, "solar-power"
    ),
    "electricity_return_low": SensorInfo(
        SensorDeviceClass.ENERGY, Unit.kwh, "solar-power"
    ),
    "electricity_return_total": SensorInfo(
        SensorDeviceClass.ENERGY, Unit.kwh, "transmission-tower-import"
    ),
    "electricity_price_low": SensorInfo(
        SensorDeviceClass.MONETARY, Unit.eur_kwh, "currency-eur"
    ),
    "electricity_price_high": SensorInfo(
        SensorDeviceClass.MONETARY, Unit.eur_kwh, "currency-eur"
    ),
    "electricity_price_single": SensorInfo(
        SensorDeviceClass.MONETARY, Unit.eur_kwh, "currency-eur"
    ),
    "electricity_return_price": SensorInfo(
        SensorDeviceClass.MONETARY, Unit.eur_kwh, "currency-eur"
    ),
    "gas_consumption": SensorInfo(SensorDeviceClass.GAS, Unit.m3, "fire"),
    "gas_price": SensorInfo(SensorDeviceClass.MONETARY, Unit.eur_m3, "currency-eur"),
}


# noinspection PyUnusedLocal
def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: t.Optional[DiscoveryInfoType] = None,
) -> None:
    name = config.get(CONF_NAME)
    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)
    contract_id = config.get(CONF_OVEREENKOMST_ID)

    if username == CONF_USERNAME:
        username = None
    if password == CONF_PASSWORD:
        password = None
    if contract_id == CONF_OVEREENKOMST_ID:
        contract_id = None

    _LOGGER.debug("Set up platform")
    greenchoice_api = GreenchoiceApiData(contract_id, username, password)

    throttled_api_update(greenchoice_api)

    sensors = [
        GreenchoiceSensor(
            greenchoice_api,
            name,
            sensor_name,
        )
        for sensor_name in sensor_infos.keys()
    ]

    add_entities(sensors, True)


@Throttle(MIN_TIME_BETWEEN_UPDATES)
def throttled_api_update(api):
    _LOGGER.debug("Throttled update called.")
    api_result = api.update()
    _LOGGER.debug(f"{api_result=}")
    return api_result


class GreenchoiceSensor(SensorEntity):
    def __init__(
        self,
        greenchoice_api,
        name,
        measurement_type,
    ):
        self._api = greenchoice_api
        self._measurement_type = measurement_type
        self._measurement_date = None
        self._measurement_date_key = (
            "measurement_date_electricity"
            if "electricity" in self._measurement_type
            else "measurement_date_gas"
        )

        sensor_info = sensor_infos[self._measurement_type]

        self._attr_unique_id = f"{slugify(name)}_{measurement_type}"
        self._attr_name = self._attr_unique_id
        self._attr_icon = f"mdi:{sensor_info.icon}"

        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_device_class = sensor_info.device_class
        self._attr_native_value = STATE_UNKNOWN
        self._attr_native_unit_of_measurement = sensor_info.unit

    def update(self):
        """Get the latest data from the Greenchoice API."""
        _LOGGER.debug(f"Updating {self.name}")
        api_result = throttled_api_update(self._api) or self._api.result

        if not api_result or self._measurement_type not in api_result:
            return

        self._attr_native_value = api_result[self._measurement_type]
        self._measurement_date = api_result[self._measurement_date_key]

    @property
    def measurement_type(self):
        return self._measurement_type

    @property
    def measurement_date(self):
        return self._measurement_date
