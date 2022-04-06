import logging
from datetime import timedelta, datetime
from urllib.parse import urlparse, parse_qs

import bs4
import homeassistant.helpers.config_validation as cv
import requests
import voluptuous as vol
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass, PLATFORM_SCHEMA
from homeassistant.const import (CONF_NAME, STATE_UNKNOWN)
from homeassistant.exceptions import PlatformNotReady
from homeassistant.util import Throttle, slugify

__version__ = '0.0.2'

_LOGGER = logging.getLogger(__name__)
_RESOURCE = 'https://mijn.greenchoice.nl'

CONF_OVEREENKOMST_ID = 'overeenkomst_id'
CONF_USERNAME = 'username'
CONF_PASSWORD = 'password'

DEFAULT_NAME = 'Energieverbruik'
DEFAULT_DATE_FORMAT = '%y-%m-%dT%H:%M:%S'

ATTR_NAME = 'name'
ATTR_UPDATE_CYCLE = 'update_cycle'
ATTR_ICON = 'icon'
ATTR_MEASUREMENT_DATE = 'date'
ATTR_NATIVE_UNIT_OF_MEASUREMENT = 'native_unit_of_measurement'
ATTR_STATE_CLASS = 'state_class'

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=3600)
MEASUREMENT_TYPES = {
    1: 'consumption_high',
    2: 'consumption_low',
    3: 'return_high',
    4: 'return_low'
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_USERNAME, default=CONF_USERNAME): cv.string,
    vol.Optional(CONF_PASSWORD, default=CONF_USERNAME): cv.string,
    vol.Optional(CONF_OVEREENKOMST_ID, default=CONF_OVEREENKOMST_ID): cv.string,
})


# noinspection PyUnusedLocal
def setup_platform(hass, config, add_entities, discovery_info=None):
    name = config.get(CONF_NAME)
    overeenkomst_id = config.get(CONF_OVEREENKOMST_ID)
    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)

    greenchoice_api = GreenchoiceApiData(overeenkomst_id, username, password)

    greenchoice_api.update()

    if greenchoice_api is None:
        raise PlatformNotReady

    sensors = [
        GreenchoiceSensor(greenchoice_api, name, overeenkomst_id, username, password, 'currentGas'),
        GreenchoiceSensor(greenchoice_api, name, overeenkomst_id, username, password, 'energy_consumption_high'),
        GreenchoiceSensor(greenchoice_api, name, overeenkomst_id, username, password, 'energy_consumption_low'),
        GreenchoiceSensor(greenchoice_api, name, overeenkomst_id, username, password, 'energy_consumption_total'),
        GreenchoiceSensor(greenchoice_api, name, overeenkomst_id, username, password, 'energy_return_high'),
        GreenchoiceSensor(greenchoice_api, name, overeenkomst_id, username, password, 'energy_return_low'),
        GreenchoiceSensor(greenchoice_api, name, overeenkomst_id, username, password, 'energy_return_total'),
        GreenchoiceSensor(greenchoice_api, name, overeenkomst_id, username, password, 'gas_consumption'),
    ]
    add_entities(sensors, True)


def _get_verification_token(html_txt: str):
    soup = bs4.BeautifulSoup(html_txt, 'html.parser')
    token_elem = soup.find('input', {'name': '__RequestVerificationToken'})

    return token_elem.attrs.get('value')


def _get_oidc_params(html_txt: str):
    soup = bs4.BeautifulSoup(html_txt, 'html.parser')

    code_elem = soup.find('input', {'name': 'code'})
    scope_elem = soup.find('input', {'name': 'scope'})
    state_elem = soup.find('input', {'name': 'state'})
    session_state_elem = soup.find('input', {'name': 'session_state'})

    if not (code_elem and scope_elem and state_elem and session_state_elem):
        raise LoginError('Login failed, check your credentials?')

    return {
        'code': code_elem.attrs.get('value'),
        'scope': scope_elem.attrs.get('value').replace(' ', '+'),
        'state': state_elem.attrs.get('value'),
        'session_state': session_state_elem.attrs.get('value')
    }


class LoginError(Exception):
    pass


class GreenchoiceSensor(SensorEntity):
    def __init__(self, greenchoice_api, name, overeenkomst_id, username, password, measurement_type, ):
        self._json_data = greenchoice_api
        self._name = name
        self._unique_id = f"{slugify(name)}_{measurement_type}"
        self._overeenkomst_id = overeenkomst_id
        self._username = username
        self._password = password
        self._measurement_type = measurement_type
        self._measurement_date = None
        self._native_unit_of_measurement = None
        self._state = None
        self._icon = None
        self._device_class = SensorDeviceClass.ENERGY
        self._state_class = SensorStateClass.TOTAL

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
            ATTR_STATE_CLASS: self._state_class
        }

    def update(self):
        """Get the latest data from the Greenchoice API."""
        self._json_data.update()

        data = self._json_data.result

        if self._username == CONF_USERNAME or self._username is None:
            _LOGGER.error('Need a username!')
        elif self._password == CONF_PASSWORD or self._password is None:
            _LOGGER.error('Need a password!')
        elif self._overeenkomst_id == CONF_OVEREENKOMST_ID or self._overeenkomst_id is None:
            _LOGGER.error('Need a overeenkomst id (see docs how to get one)!')

        if data is None or self._measurement_type not in data:
            self._state = STATE_UNKNOWN
        else:
            self._state = data[self._measurement_type]
            self._measurement_date = data['measurement_date_electricity']

        if self._measurement_type == 'energy_consumption_high':
            self._icon = 'mdi:weather-sunset-up'
            self._name = 'energy_consumption_high'
            self._native_unit_of_measurement = 'kWh'
        elif self._measurement_type == 'energy_consumption_low':
            self._icon = 'mdi:weather-sunset-down'
            self._name = 'energy_consumption_low'
            self._native_unit_of_measurement = 'kWh'
        elif self._measurement_type == 'energy_consumption_total':
            self._icon = 'mdi:transmission-tower-export'
            self._name = 'energy_consumption_total'
            self._native_unit_of_measurement = 'kWh'
        elif self._measurement_type == 'energy_return_high':
            self._icon = 'mdi:solar-power'
            self._name = 'energy_return_high'
            self._native_unit_of_measurement = 'kWh'
        elif self._measurement_type == 'energy_return_low':
            self._icon = 'mdi:solar-panel'
            self._name = 'energy_return_low'
            self._native_unit_of_measurement = 'kWh'
        elif self._measurement_type == 'energy_return_total':
            self._icon = 'mdi:transmission-tower-import'
            self._name = 'energy_return_total'
            self._native_unit_of_measurement = 'kWh'
        elif self._measurement_type == 'gas_consumption':
            self._measurement_date = data['measurement_date_gas']
            self._icon = 'mdi:fire'
            self._name = 'gas_consumption'
            self._device_class = SensorDeviceClass.GAS
            self._native_unit_of_measurement = 'm³'


class GreenchoiceApiData:
    def __init__(self, overeenkomst_id, username, password):
        self._resource = _RESOURCE
        self._overeenkomst_id = overeenkomst_id
        self._username = username
        self._password = password

        self.result = {}
        self.session = requests.Session()

    def _activate_session(self):
        _LOGGER.info('Retrieving login cookies')
        _LOGGER.debug('Purging existing session')
        self.session.close()
        self.session = requests.Session()

        # first, get the login cookies and form data
        login_page = self.session.get(_RESOURCE)

        login_url = login_page.url
        return_url = parse_qs(urlparse(login_url).query).get('ReturnUrl', '')
        token = _get_verification_token(login_page.text)

        # perform actual sign in
        _LOGGER.debug('Logging in with username and password')
        login_data = {
            'ReturnUrl': return_url,
            'Username': self._username,
            'Password': self._password,
            '__RequestVerificationToken': token,
            'RememberLogin': True
        }
        auth_page = self.session.post(login_page.url, data=login_data)

        # exchange oidc params for a login cookie (automatically saved in session)
        _LOGGER.debug('Signing in using OIDC')
        oidc_params = _get_oidc_params(auth_page.text)
        self.session.post(f'{_RESOURCE}/signin-oidc', data=oidc_params)

        _LOGGER.debug('Login success')

    def request(self, method, endpoint, data=None, _retry_count=1):
        _LOGGER.debug(f'Request: {method} {endpoint}')
        try:
            target_url = _RESOURCE + endpoint
            r = self.session.request(method, target_url, json=data)

            if r.status_code == 403 or len(r.history) > 1:  # sometimes we get redirected on token expiry
                _LOGGER.debug('Access cookie expired, triggering refresh')
                try:
                    self._activate_session()
                    return self.request(method, endpoint, data, _retry_count)
                except LoginError:
                    _LOGGER.error('Login failed! Please check your credentials and try again.')
                    return None

            r.raise_for_status()
        except requests.HTTPError as e:
            _LOGGER.error(f'HTTP Error: {e}')
            _LOGGER.error([c.name for c in self.session.cookies])
            if _retry_count == 0:
                return None

            _LOGGER.debug('Retrying request')
            return self.request(method, endpoint, data, _retry_count - 1)

        return r

    def microbus_request(self, name, message=None):
        if not message:
            message = {}

        payload = {
            'name': name,
            'message': message
        }
        return self.request('POST', '/microbus/request', payload)

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        self.result = {}

        _LOGGER.debug('Retrieving meter values')
        meter_values_request = self.microbus_request('OpnamesOphalen')
        if not meter_values_request:
            _LOGGER.error('Error while retrieving meter values!')
            return

        try:
            monthly_values = meter_values_request.json()
        except requests.exceptions.JSONDecoderError:
            _LOGGER.error('Could not update meter values: request returned no valid JSON')
            _LOGGER.error('Returned data: ' + meter_values_request.text)
            return

        # parse energy data
        electricity_values = monthly_values['model']['productenOpnamesModel'][0]['opnamesJaarMaandModel']
        current_month = sorted(electricity_values, key=lambda m: (m['jaar'], m['maand']), reverse=True)[0]
        current_day = sorted(
            current_month['opnames'],
            key=lambda d: datetime.strptime(d['opnameDatum'], '%Y-%m-%dT%H:%M:%S'),
            reverse=True
        )[0]

        # process energy types
        for measurement in current_day['standen']:
            measurement_type = MEASUREMENT_TYPES[measurement['telwerk']]
            self.result['energy_' + measurement_type] = measurement['waarde']

        # total energy count
        self.result['energy_consumption_total'] = self.result['energy_consumption_high'] + \
            self.result['energy_consumption_low']
        self.result['energy_return_total'] = self.result['energy_return_high'] + self.result['energy_return_low']

        self.result['measurement_date_electricity'] = datetime.strptime(current_day['opnameDatum'], '%Y-%m-%dT%H:%M:%S')

        # process gas
        if monthly_values['model']['heeftGas']:
            gas_values = monthly_values['model']['productenOpnamesModel'][1]['opnamesJaarMaandModel']
            current_month = sorted(gas_values, key=lambda m: (m['jaar'], m['maand']), reverse=True)[0]
            current_day = sorted(
                current_month['opnames'],
                key=lambda d: datetime.strptime(d['opnameDatum'], '%Y-%m-%dT%H:%M:%S'),
                reverse=True
            )[0]

            measurement = current_day['standen'][0]
            if measurement['telwerk'] == 5:
                self.result['gas_consumption'] = measurement['waarde']

            self.result['measurement_date_gas'] = datetime.strptime(current_day['opnameDatum'], '%Y-%m-%dT%H:%M:%S')
