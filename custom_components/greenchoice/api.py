import logging
from datetime import datetime, UTC
from typing import Union
from urllib.parse import urlencode

import requests

from .auth import Auth
from .model import MeterReadings, Reading, Rates, Profile
from .model import Preferences
from .util import curl_dump

# Force the log level for easy debugging.
# None          - Don't force any log level and use the defaults.
# logging.DEBUG - Force debug logging.
#   See the logging package for additional log levels.
_FORCE_LOG_LEVEL: Union[int, None] = None
_LOGGER = logging.getLogger(__name__)
if _FORCE_LOG_LEVEL is not None:
    _LOGGER.setLevel(_FORCE_LOG_LEVEL)

BASE_URL = "https://mijn.greenchoice.nl"


class ApiError(Exception):
    def __init__(self, message: str):
        _LOGGER.error(message)
        super(message)


class GreenchoiceApi:
    def __init__(self, username: str, password: str):
        self.auth = Auth(BASE_URL, username, password)
        self.preferences: Preferences | None = None

        self.result = {}

    def _authenticated_request(
        self, method: str, endpoint: str, data=None, json=None
    ) -> requests.models.Response:
        _LOGGER.debug(
            f"Request: {method} {endpoint} {data if data is not None else json}"
        )
        response = self.auth.session.request(method, endpoint, data=data, json=json)
        if self.auth.is_session_expired(response):
            self.session = self.auth.refresh_session()
            response = self.auth.session.request(method, endpoint, data=data, json=json)

        _LOGGER.debug(curl_dump(response.request))

        return response

    def request(
        self, method: str, endpoint: str, data=None, _retry_count=2
    ) -> requests.Response:
        try:
            target_url = BASE_URL + endpoint
            response = self._authenticated_request(method, target_url, json=data)

            if len(response.history) > 1:
                _LOGGER.debug("Response history len > 1. %s", response.history)

            # Some api's may not work and there might be fallbacks for them
            if response.status_code == 404:
                return response

            response.raise_for_status()
        except requests.HTTPError as e:
            _LOGGER.error("HTTP Error: %s", e)
            _LOGGER.error("Cookies: %s", [c.name for c in self.session.cookies])
            if _retry_count == 0:
                raise ApiError(f"HTTP Error: {e}")

            _LOGGER.debug("Retrying request")
            return self.request(method, endpoint, data, _retry_count - 1)

        _LOGGER.debug("Request success")
        return response

    @staticmethod
    def _validate_response(response: requests.Response) -> dict:
        if not response:
            raise ApiError("Error retrieving response!")

        try:
            response_json = response.json()
        except requests.exceptions.JSONDecodeError as e:
            raise ApiError("Could not parse response: invalid JSON", e)

        return response_json

    def microbus_init(self) -> dict:
        response = self.request("GET", "/microbus/init")
        return self._validate_response(response)

    def get_preferences(self) -> Preferences:
        preferences_json = self._validate_response(
            self.request("GET", f"/api/v2/Preferences/")
        )
        return Preferences.from_dict(preferences_json)

    def get_profiles(self) -> list[Profile]:
        profiles_json = self._validate_response(
            self.request("GET", f"/api/v2/Profiles/")
        )
        return [Profile.from_dict(p) for p in profiles_json]

    def get_meter_readings(self) -> MeterReadings:
        meter_json = self._validate_response(
            self.request(
                "GET",
                (
                    "/api/v2/MeterReadings/"
                    f"{datetime.now(UTC).year}/"
                    f"{self.preferences.subject.customerNumber}/"
                    f"{self.preferences.subject.agreementId}"
                ),
            )
        )

        return MeterReadings.from_dict(meter_json)

    def get_ref_ids(self) -> tuple[str, str]:
        init_config = self.microbus_init()

        customer_id = self.preferences.subject.customerNumber
        contract_id = self.preferences.subject.agreementId
        ref_id_electricity = ""
        ref_id_gas = ""

        all_client_details = init_config.get("klantgegevens")
        for client_details in all_client_details:
            if client_details.get("klantnummer") == customer_id:
                client_addresses = client_details.get("adressen")
                for client_address in client_addresses:
                    if (
                        client_address.get("klantnummer") == customer_id
                        and client_address.get("overeenkomstId") == contract_id
                    ):

                        contracts = client_address.get("contracten")
                        for contract in contracts:
                            if (
                                contract.get("marktsegment") == "E"
                            ):  # E stands for electricity, G for gas
                                ref_id_electricity = contract.get("refId")
                            else:
                                ref_id_gas = contract.get("refId")

        return ref_id_electricity, ref_id_gas

    def get_rates(self) -> Rates:

        profiles = self.get_profiles()
        current_profile: Profile | None = None
        for profile in profiles:
            if (
                profile.customerNumber == self.preferences.subject.customerNumber
                and profile.agreementId == self.preferences.subject.agreementId
            ):
                current_profile = profile
                break
        if not current_profile:
            raise ApiError("Cant find profile")

        ref_id_electricity, ref_id_gas = self.get_ref_ids()

        req_data = {
            "HouseNumber": current_profile.houseNumber,
            "ZipCode": current_profile.postalCode,
        }
        if ref_id_electricity:
            req_data["ReferenceIdElectricity"] = ref_id_electricity
            req_data["AgreementIdElectricity"] = current_profile.agreementId
        if ref_id_gas:
            req_data["ReferenceIdGas"] = ref_id_gas
            req_data["AgreementIdGas"] = current_profile.agreementId

        response = self.request(
            "GET",
            f"/api/v2/Rates/{current_profile.customerNumber}?{urlencode(req_data)}",
        )
        if response.status_code == 404:
            response = self.request("GET", "/api/tariffs")
        pricing_details = self._validate_response(response)
        if "huidig" in pricing_details:
            pricing_details = pricing_details["huidig"]

        return Rates.from_dict(pricing_details)

    def update(self) -> dict:
        self.result = {}
        try:
            self.preferences = self.get_preferences()
        except ApiError:
            _LOGGER.error("Cant get preferences")
            return self.result

        try:
            self.update_usage_values(self.result)
        except ApiError:
            _LOGGER.error("Cant update usage values")
            pass

        try:
            self.update_contract_values(self.result)
        except ApiError:
            _LOGGER.error("Cant update contract values")
            pass

        return self.result

    def update_usage_values(self, result: dict) -> None:
        _LOGGER.debug("Retrieving meter values")

        meter_readings = self.get_meter_readings()

        electricity_reading: Reading | None = meter_readings.last_electricity_reading
        gas_reading: Reading | None = meter_readings.last_gas_reading

        if electricity_reading:
            result["electricity_consumption_low"] = (
                electricity_reading.offPeakConsumption
            )
            result["electricity_consumption_high"] = (
                electricity_reading.normalConsumption
            )
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

    def update_contract_values(self, result: dict) -> None:
        _LOGGER.debug("Retrieving contract values")

        pricing_details = self.get_rates()

        if pricing_details.stroom:
            result["electricity_price_single"] = (
                pricing_details.stroom.leveringEnkelAllIn
            )
            result["electricity_price_low"] = pricing_details.stroom.leveringLaagAllIn
            result["electricity_price_high"] = pricing_details.stroom.leveringHoogAllIn
            result["electricity_return_price"] = (
                pricing_details.stroom.terugleverVergoeding
            )

        if pricing_details.gas:
            result["gas_price"] = pricing_details.gas.leveringAllIn
