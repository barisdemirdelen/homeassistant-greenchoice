import logging
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import bs4
import requests

_LOGGER = logging.getLogger(__name__)
_RESOURCE = "https://mijn.greenchoice.nl"

MEASUREMENT_TYPES = {
    1: "consumption_high",
    2: "consumption_low",
    3: "return_high",
    4: "return_low",
}


def _get_verification_token(html_txt: str):
    soup = bs4.BeautifulSoup(html_txt, "html.parser")
    token_elem = soup.find("input", {"name": "__RequestVerificationToken"})

    return token_elem.attrs.get("value")


def _get_oidc_params(html_txt: str):
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
    def __init__(self, overeenkomst_id, username, password):
        self._resource = _RESOURCE
        self._overeenkomst_id = overeenkomst_id
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
        if not self._overeenkomst_id:
            _LOGGER.error("Need a overeenkomst id (see docs how to get one)!")
            return False
        return True

    def _activate_session(self):
        _LOGGER.info("Retrieving login cookies")
        _LOGGER.debug("Purging existing session")
        if self.session:
            self.session.close()
        self.session = requests.Session()

        # first, get the login cookies and form data
        login_page = self.session.get(_RESOURCE)

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
        auth_page = self.session.post(login_page.url, data=login_data)

        # exchange oidc params for a login cookie (automatically saved in session)
        _LOGGER.debug("Signing in using OIDC")
        oidc_params = _get_oidc_params(auth_page.text)
        self.session.post(f"{_RESOURCE}/signin-oidc", data=oidc_params)

        _LOGGER.debug("Login success")

    def request(self, method, endpoint, data=None, _retry_count=2):
        _LOGGER.debug(f"Request: {method} {endpoint} {data}")
        try:
            target_url = _RESOURCE + endpoint
            r = self.session.request(method, target_url, json=data)

            # Sometimes we get redirected on token expiry
            if r.status_code == 403 or r.status_code == 500 or len(r.history) > 1:
                _LOGGER.debug("Access cookie expired, triggering refresh")
                try:
                    self._activate_session()
                    if _retry_count == 0:
                        r.raise_for_status()
                    return self.request(method, endpoint, data, _retry_count - 1)
                except LoginError:
                    _LOGGER.error(
                        "Login failed! Please check your credentials and try again."
                    )
                    return None

            r.raise_for_status()
        except requests.HTTPError as e:
            _LOGGER.error(f"HTTP Error: {e}")
            _LOGGER.error([c.name for c in self.session.cookies])
            if _retry_count == 0:
                return None

            _LOGGER.debug("Retrying request")
            return self.request(method, endpoint, data, _retry_count - 1)

        return r

    def microbus_request(self, name, message=None):
        if not message:
            message = {}

        payload = {"name": name, "message": message}
        return self.request("POST", "/microbus/request", payload)

    def update(self):
        self.result = {}
        self.update_usage_values(self.result)
        self.update_contract_values(self.result)
        return self.result

    def update_usage_values(self, result):
        _LOGGER.debug("Retrieving meter values")
        meter_values_request = self.microbus_request("OpnamesOphalen")
        if not meter_values_request:
            _LOGGER.error("Error while retrieving meter values!")
            return

        try:
            monthly_values = meter_values_request.json()
        except requests.exceptions.JSONDecoderError:
            _LOGGER.error(
                "Could not update meter values: request returned no valid JSON"
            )
            _LOGGER.error("Returned data: " + meter_values_request.text)
            return

        products = monthly_values["model"]["productenOpnamesModel"]

        # parse energy data
        electricity_values = products[0]["opnamesJaarMaandModel"]
        measurements, measurement_date = self._get_last_measurements(electricity_values)

        # process energy types
        for measurement in measurements:
            measurement_type = MEASUREMENT_TYPES[measurement["telwerk"]]
            result["electricity_" + measurement_type] = measurement["waarde"]

        # total energy count
        result["electricity_consumption_total"] = (
            result["electricity_consumption_high"]
            + result["electricity_consumption_low"]
        )
        result["electricity_return_total"] = (
            result["electricity_return_high"] + result["electricity_return_low"]
        )

        result["measurement_date_electricity"] = measurement_date

        # process gas
        if monthly_values["model"]["heeftGas"]:
            gas_values = products[1]["opnamesJaarMaandModel"]
            measurements, measurement_date = self._get_last_measurements(gas_values)
            for measurement in measurements:
                if measurement["telwerk"] == 5:
                    result["gas_consumption"] = measurement["waarde"]

            result["measurement_date_gas"] = measurement_date

    def update_contract_values(self, result):
        _LOGGER.debug("Retrieving contract values")

        contract_values_request = self.microbus_request("GetTariefOvereenkomst")
        if not contract_values_request:
            _LOGGER.error("Error while retrieving contract values!")
            return

        try:
            contract_values = contract_values_request.json()
        except requests.exceptions.JSONDecoderError:
            _LOGGER.error(
                "Could not update meter values: request returned no valid JSON"
            )
            _LOGGER.error(f"Returned data: {contract_values_request.text}")
            return

        electricity = contract_values.get("stroom")
        if electricity:
            result["electricity_price_single"] = electricity["leveringEnkelAllin"]
            result["electricity_price_low"] = electricity["leveringLaagAllin"]
            result["electricity_price_high"] = electricity["leveringHoogAllin"]
            result["electricity_return_price"] = electricity["terugleververgoeding"]

        gas = contract_values.get("gas")
        if gas:
            result["gas_price"] = gas["leveringAllin"]

    @staticmethod
    def _get_last_measurements(values):
        months = sorted(values, key=lambda m: (m["jaar"], m["maand"]), reverse=True)
        for current_month in months:
            if not current_month.get("opnames"):
                continue

            days = list(
                sorted(
                    current_month["opnames"],
                    key=lambda d: datetime.strptime(
                        d["opnameDatum"], "%Y-%m-%dT%H:%M:%S"
                    ),
                    reverse=True,
                )
            )

            if not days:
                continue

            current_day = days[0]

            measurements = current_day["standen"]
            measurement_date = datetime.strptime(
                current_day["opnameDatum"], "%Y-%m-%dT%H:%M:%S"
            )

            return measurements, measurement_date

        _LOGGER.error("No measurements found")
