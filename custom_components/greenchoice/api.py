import json
import logging
from datetime import datetime, UTC
from typing import Union
from urllib.parse import parse_qs, urlparse, urlencode

import bs4
import requests
import re

from pydantic import ValidationError

from .model import Preferences, MeterReadings, Reading, Rates

_LOGGER = logging.getLogger(__name__)
# Force the log level for easy debugging.
# None          - Don't force any log level and use the defaults.
# logging.DEBUG - Force debug logging.
#   See the logging package for additional log levels.
_FORCE_LOG_LEVEL: Union[int, None] = None
if _FORCE_LOG_LEVEL is not None:
    _LOGGER.setLevel(_FORCE_LOG_LEVEL)

BASE_URL = "https://mijn.greenchoice.nl"


def _curl_dump(req: requests.Request) -> str:
    # Slightly modified curl dump borrowed from this
    #   Stack Overflow answer: https://stackoverflow.com/a/17936634/4925795
    command = "curl -X {method} -H {headers} -d '{data}' '{uri}'"
    method = req.method
    uri = req.url
    data = req.body
    if isinstance(data, bytes):
        data = json.dumps(json.loads(data))
    headers = ['"{0}: {1}"'.format(k, v) for k, v in req.headers.items()]
    headers = " -H ".join(headers)
    return command.format(method=method, headers=headers, data=data, uri=uri)


def _get_verification_token(html_txt: str) -> str:
    soup = bs4.BeautifulSoup(html_txt, "html.parser")
    token_elem = soup.find("input", {"name": "__RequestVerificationToken"})

    return token_elem.attrs.get("value")


def _get_oidc_params(html_txt: str) -> dict[str, str]:
    soup = bs4.BeautifulSoup(html_txt, "html.parser")

    code_elem = soup.find("input", {"name": "code"})
    scope_elem = soup.find("input", {"name": "scope"})
    state_elem = soup.find("input", {"name": "state"})
    session_state_elem = soup.find("input", {"name": "session_state"})

    if not (code_elem and scope_elem and state_elem and session_state_elem):
        raise LoginError("Login failed, check your credentials?")

    return {
        "code": code_elem.attrs.get("value"),
        "scope": scope_elem.attrs.get("value").replace(" ", "+"),
        "state": state_elem.attrs.get("value"),
        "session_state": session_state_elem.attrs.get("value"),
    }


class LoginError(Exception):
    pass


class GreenchoiceApiData:
    def __init__(self, username: str, password: str):
        self._username = username
        self._password = password

        if not self._check_login():
            raise AttributeError("Configuration is incomplete")

        self.result = {}
        self.session = None
        self._activate_session()

    def _check_login(self):
        if not self._username:
            _LOGGER.error("Need a username!")
            return False
        if not self._password:
            _LOGGER.error("Need a password!")
            return False
        return True

    def __session_request(
        self, method: str, endpoint: str, data=None, json=None
    ) -> requests.models.Response:
        _LOGGER.debug(
            f"Request: {method} {endpoint} {data if data is not None else json}"
        )
        response = self.session.request(method, endpoint, data=data, json=json)

        try:
            _LOGGER.debug(_curl_dump(response.request))
        except Exception:  # NOSONAR Catch all exceptions here because
            #   execution should not stop in case of curl dump errors.
            _LOGGER.warning("Logging curl dump failed, gracefully ignoring.")

        return response

    def _activate_session(self):
        _LOGGER.info("Retrieving login cookies")
        if self.session:
            _LOGGER.debug("Purging existing session")
            self.session.close()
        self.session = requests.Session()

        # first, get the login cookies and form data
        login_page = self.__session_request("GET", BASE_URL)

        login_url = login_page.url
        return_url = parse_qs(urlparse(login_url).query).get("ReturnUrl", "")
        token = _get_verification_token(login_page.text)

        # perform actual sign in
        _LOGGER.debug("Logging in with username and password")
        login_data = {
            "ReturnUrl": return_url,
            "Username": self._username,
            "Password": self._password,
            "__RequestVerificationToken": token,
            "RememberLogin": True,
        }
        auth_page = self.__session_request("POST", login_page.url, data=login_data)

        # exchange oidc params for a login cookie (automatically saved in session)
        _LOGGER.debug("Signing in using OIDC")
        oidc_params = _get_oidc_params(auth_page.text)
        self.__session_request("POST", f"{BASE_URL}/signin-oidc", data=oidc_params)

        _LOGGER.debug("Login success")

    def request(self, method, endpoint, data=None, _retry_count=2):
        try:
            target_url = BASE_URL + endpoint
            response = self.__session_request(method, target_url, json=data)

            if len(response.history) > 1:
                _LOGGER.debug("Response history len > 1. %s", response.history)

            session_expired = False
            # If the session expired, the client is redirected to the SSO login.
            for history_response in response.history:
                if history_response.status_code != 302:
                    continue
                location_header: str = history_response.headers.get("Location")
                if location_header is not None and re.search(
                    "^.*://sso.greenchoice.nl/connect/authorize.*$", location_header
                ):
                    session_expired = True
                    break

            # Sometimes we get Forbidden on token expiry
            if response.status_code == 403:
                session_expired = True

            if session_expired:
                _LOGGER.debug("Session possibly expired, triggering refresh")
                try:
                    self._activate_session()
                except LoginError:
                    _LOGGER.error(
                        "Login failed! Please check your credentials and try again."
                    )
                    return None
                response = self.__session_request(method, target_url, json=data)

            # Some api's may not work and there might be fallbacks for them
            if response.status_code == 404:
                return response

            response.raise_for_status()
        except requests.HTTPError as e:
            _LOGGER.error("HTTP Error: %s", e)
            _LOGGER.error("Cookies: %s", [c.name for c in self.session.cookies])
            if _retry_count == 0:
                return None

            _LOGGER.debug("Retrying request")
            return self.request(method, endpoint, data, _retry_count - 1)

        _LOGGER.debug("Request success")
        return response

    def _validate_response(self, response):
        if not response:
            _LOGGER.error("Error retrieving response!")
            return {}

        try:
            response_json = response.json()
        except requests.exceptions.JSONDecodeError:
            _LOGGER.error("Could not parse response: invalid JSON")
            return {}

        return response_json

    def microbus_init(self):
        response = self.request("GET", "/microbus/init")
        return self._validate_response(response)

    def update(self):
        self.result = {}
        self.update_usage_values(self.result)
        self.update_contract_values(self.result)
        return self.result

    def update_usage_values(self, result):
        _LOGGER.debug("Retrieving meter values")

        preferences_json = self._validate_response(
            self.request("GET", f"/api/v2/Preferences/")
        )
        try:
            preferences = Preferences.from_dict(preferences_json)
        except ValidationError:
            _LOGGER.error("Could not validate profile")
            return

        meter_json = self._validate_response(
            self.request(
                "GET",
                (
                    "/api/v2/MeterReadings/"
                    f"{datetime.now(UTC).year}/"
                    f"{preferences.subject.customerNumber}/"
                    f"{preferences.subject.agreementId}"
                ),
            )
        )

        try:
            meter_readings = MeterReadings.from_dict(meter_json)
        except ValidationError:
            _LOGGER.error("Could not validate meter readings")
            return

        electricity_reading: Reading | None = None
        gas_reading: Reading | None = None
        for product in meter_readings.productTypes:
            for month in sorted(product.months, key=lambda p: p.month, reverse=True):
                if month.readings:
                    last_reading = sorted(month.readings, key=lambda r: r.readingDate)[
                        -1
                    ]
                    if product.productType.lower() == "stroom":
                        electricity_reading = last_reading
                    if product.productType.lower() == "gas":
                        gas_reading = last_reading
                    break

        if electricity_reading:
            result[
                "electricity_consumption_low"
            ] = electricity_reading.offPeakConsumption
            result[
                "electricity_consumption_high"
            ] = electricity_reading.normalConsumption
            result["electricity_consumption_total"] = (
                electricity_reading.offPeakConsumption
                + electricity_reading.normalConsumption
            )
            result["electricity_return_low"] = electricity_reading.offPeakFeedIn
            result["electricity_return_high"] = electricity_reading.normalFeedIn
            result["electricity_return_total"] = (
                electricity_reading.offPeakFeedIn + electricity_reading.normalFeedIn
            )
            result["measurement_date_electricity"] = electricity_reading.readingDate

        if gas_reading:
            result["gas_consumption"] = gas_reading.gas
            result["measurement_date_gas"] = gas_reading.readingDate

    def update_contract_values(self, result):
        _LOGGER.debug("Retrieving contract values")

        init_config = self.microbus_init()

        current_contract_details = init_config.get("profile").get(
            "voorkeursOvereenkomst"
        )
        customer_id = current_contract_details.get("klantnummer")
        contract_id = current_contract_details.get("overeenkomstId")
        ref_id_electricity = ""
        ref_id_gas = ""
        house_number = ""
        zip_code = ""

        all_client_details = init_config.get("klantgegevens")
        for client_details in all_client_details:
            if client_details.get("klantnummer") == customer_id:
                client_addresses = client_details.get("adressen")
                for client_address in client_addresses:
                    if (
                        client_address.get("klantnummer") == customer_id
                        and client_address.get("overeenkomstId") == contract_id
                    ):
                        house_number = client_address.get("huisnummer")
                        zip_code = client_address.get("postcode")

                        contracts = client_address.get("contracten")
                        for contract in contracts:
                            if (
                                contract.get("marktsegment") == "E"
                            ):  # E stands for electricity, G for gas
                                ref_id_electricity = contract.get("refId")
                            else:
                                ref_id_gas = contract.get("refId")

        req_data = {
            "HouseNumber": house_number,
            "ZipCode": zip_code,
        }
        if ref_id_electricity:
            req_data["ReferenceIdElectricity"] = ref_id_electricity
            req_data["AgreementIdElectricity"] = contract_id
        if ref_id_gas:
            req_data["ReferenceIdGas"] = ref_id_gas
            req_data["AgreementIdGas"] = contract_id

        data = urlencode(req_data)
        response = self.request("GET", f"/api/v2/Rates/{customer_id}?{data}")
        if response.status_code == 404:
            response = self.request("GET", "/api/tariffs")
        pricing_details = self._validate_response(response)
        if "huidig" in pricing_details:
            pricing_details = pricing_details["huidig"]

        pricing_details = Rates.from_dict(pricing_details)

        if pricing_details.stroom:
            result[
                "electricity_price_single"
            ] = pricing_details.stroom.leveringEnkelAllIn
            result["electricity_price_low"] = pricing_details.stroom.leveringLaagAllIn
            result["electricity_price_high"] = pricing_details.stroom.leveringHoogAllIn
            result[
                "electricity_return_price"
            ] = pricing_details.stroom.terugleverVergoeding

        if pricing_details.gas:
            result["gas_price"] = pricing_details.gas.leveringAllIn
