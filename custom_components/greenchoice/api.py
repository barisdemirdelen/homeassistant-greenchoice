import logging
from datetime import datetime, UTC
from typing import Union
from urllib.parse import urlencode

import requests
from pydantic import ValidationError

from .auth import Auth
from .model import Profile, MeterReadings, Reading, Rates
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

MEASUREMENT_TYPES = {
    1: "electricity_consumption_high",
    2: "electricity_consumption_low",
    3: "electricity_return_high",
    4: "electricity_return_low",
    5: "gas_consumption",
}


class GreenchoiceApiData:
    def __init__(self, username: str, password: str):
        self._resource = BASE_URL
        self.auth = Auth(BASE_URL, username, password)

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

    def request(self, method, endpoint, data=None, _retry_count=2):
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
                return None

            _LOGGER.debug("Retrying request")
            return self.request(method, endpoint, data, _retry_count - 1)

        _LOGGER.debug("Request success")
        return response

    @staticmethod
    def _validate_response(response):
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

    def microbus_request(self, name, message=None):
        if not message:
            message = {}

        payload = {"name": name, "message": message}
        response = self.request("POST", "/microbus/request", payload)
        return self._validate_response(response)

    def update(self):
        self.result = {}
        self.update_usage_values(self.result)
        self.update_contract_values(self.result)
        return self.result

    def update_usage_values(self, result):
        _LOGGER.debug("Retrieving meter values")

        profile_json = self._validate_response(
            self.request("GET", f"/api/v2/Profiles/")
        )
        try:
            profile = Profile.from_dict(profile_json[0])
        except ValidationError:
            _LOGGER.error("Could not validate profile")
            return

        meter_json = self._validate_response(
            self.request(
                "GET",
                (
                    "/api/v2/MeterReadings/"
                    f"{datetime.now(UTC).year}/"
                    f"{profile.customerNumber}/"
                    f"{profile.agreementId}"
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
