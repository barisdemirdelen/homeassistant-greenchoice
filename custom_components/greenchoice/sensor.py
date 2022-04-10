from collections import namedtuple

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
    PLATFORM_SCHEMA,
)
from homeassistant.const import CONF_NAME, STATE_UNKNOWN
from homeassistant.exceptions import PlatformNotReady
from homeassistant.util import slugify

__version__ = "0.0.3"

from custom_components.greenchoice.api import GreenchoiceApiData, _LOGGER

CONF_OVEREENKOMST_ID = "overeenkomst_id"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

DEFAULT_NAME = "Energieverbruik"
DEFAULT_DATE_FORMAT = "%y-%m-%dT%H:%M:%S"

ATTR_NAME = "name"
ATTR_UPDATE_CYCLE = "update_cycle"
ATTR_ICON = "icon"
ATTR_MEASUREMENT_DATE = "date"
ATTR_NATIVE_UNIT_OF_MEASUREMENT = "native_unit_of_measurement"
ATTR_STATE_CLASS = "state_class"


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
def setup_platform(hass, config, add_entities, discovery_info=None):
    name = config.get(CONF_NAME)
    overeenkomst_id = config.get(CONF_OVEREENKOMST_ID)
    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)

    greenchoice_api = GreenchoiceApiData(overeenkomst_id, username, password)

    greenchoice_api.update()

    if not greenchoice_api.result:
        raise PlatformNotReady

    sensor_names = [sensor_name for sensor_name in sensor_infos.keys()]

    sensors = [
        GreenchoiceSensor(
            greenchoice_api,
            name,
            overeenkomst_id,
            username,
            password,
            sensor_name,
        )
        for sensor_name in sensor_names
    ]

    add_entities(sensors, True)


class GreenchoiceSensor(SensorEntity):
    def __init__(
        self,
        greenchoice_api,
        name,
        overeenkomst_id,
        username,
        password,
        measurement_type,
    ):
        self._api = greenchoice_api
        self._unique_id = f"{slugify(name)}_{measurement_type}"
        self._name = self._unique_id
        self._overeenkomst_id = overeenkomst_id
        self._username = username
        self._password = password
        self._measurement_type = measurement_type
        self._measurement_date = None
        self._state = None
        self._state_class = SensorStateClass.TOTAL

        sensor_info = sensor_infos[self._measurement_type]
        self._device_class = sensor_info.device_class
        self._native_unit_of_measurement = sensor_info.unit
        self._icon = f"mdi:{sensor_info.icon}"
        self._measurement_date_key = (
            "measurement_date_electricity"
            if "electricity" in self._measurement_type
            else "measurement_date_gas"
        )

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self):
        """Return the unique id of the sensor."""
        return self._unique_id

    @property
    def overeenkomst_id(self):
        return self._overeenkomst_id

    @property
    def username(self):
        return self._username

    @property
    def password(self):
        return self._password

    @property
    def icon(self):
        return self._icon

    @property
    def state(self):
        return self._state

    @property
    def device_class(self):
        return self._device_class

    @property
    def state_class(self):
        return self._state_class

    @property
    def measurement_type(self):
        return self._measurement_type

    @property
    def measurement_date(self):
        return self._measurement_date

    @property
    def native_unit_of_measurement(self):
        return self._native_unit_of_measurement

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return {
            ATTR_MEASUREMENT_DATE: self._measurement_date,
            ATTR_NATIVE_UNIT_OF_MEASUREMENT: self._native_unit_of_measurement,
            ATTR_STATE_CLASS: self._state_class,
        }

    def _check_login(self):
        if self._username == CONF_USERNAME or self._username is None:
            _LOGGER.error("Need a username!")
            return False
        elif self._password == CONF_PASSWORD or self._password is None:
            _LOGGER.error("Need a password!")
            return False
        elif (
            self._overeenkomst_id == CONF_OVEREENKOMST_ID
            or self._overeenkomst_id is None
        ):
            _LOGGER.error("Need a overeenkomst id (see docs how to get one)!")
            return False
        return True

    def update(self):
        """Get the latest data from the Greenchoice API."""
        if not self._check_login():
            return

        data = self._api.update()

        self._state = STATE_UNKNOWN
        if not data or self._measurement_type not in data:
            return

        self._state = data[self._measurement_type]
        self._measurement_date = data[self._measurement_date_key]
