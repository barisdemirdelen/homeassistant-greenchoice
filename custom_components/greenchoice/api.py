import logging
from datetime import UTC, date, datetime, timedelta
from typing import TypeVar
from zoneinfo import ZoneInfo

import aiohttp
from pydantic import BaseModel, ValidationError

from .auth import Auth
from .model import (
    Account,
    Consumptions,
    MeterReadings,
    Preferences,
    Profile,
    RateAmount,
    Rates,
    Reading,
    SensorUpdate,
)

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://mijn.greenchoice.nl"

# Rates change on Dutch calendar days, so "today" must be local to the
# supplier: between midnight and 01:00/02:00 CET/CEST, UTC is still yesterday
# and would return the previous day's rate on a tariff-change date.
SUPPLIER_TZ = ZoneInfo("Europe/Amsterdam")

T = TypeVar("T", bound=BaseModel)


def _all_in_rate(rate: RateAmount | None) -> float | None:
    """The all-in (delivery + energy tax + VAT) price the sensors report."""
    return rate.all_in_rate_including_vat if rate else None


class ApiError(Exception):
    def __init__(self, message: str):
        _LOGGER.error(message)
        super().__init__(message)


class GreenchoiceApi:
    def __init__(
        self,
        username: str,
        password: str,
        customer_number: int | None = None,
        agreement_id: int | None = None,
    ):
        self.customer_number: int | None = customer_number
        self.agreement_id: int | None = agreement_id
        self.result: SensorUpdate = SensorUpdate()
        self._auth = Auth(BASE_URL, username, password)

    async def __aenter__(self):
        """Async context manager entry."""
        await self._auth.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self._auth.__aexit__(exc_type, exc_val, exc_tb)

    async def _authenticated_request(
        self, method: str, endpoint: str, data=None, json=None, _retry_count=2
    ) -> dict:
        """Async authenticated request."""
        _LOGGER.debug(
            f"Async Request: {method} {endpoint} {data if data is not None else json}"
        )

        session = self._auth.session

        try:
            async with session.request(
                method,
                endpoint,
                data=data,
                json=json,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                # Check if session expired
                if response.status in (401, 403):
                    # Refresh session synchronously (Auth class is sync)
                    await self._auth.refresh_session()

                    async with session.request(
                        method,
                        endpoint,
                        data=data,
                        json=json,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as retry_response:
                        if retry_response.status == 404:
                            _LOGGER.warning("Endpoint not found: %s", endpoint)
                            return {}
                        retry_response.raise_for_status()
                        return await retry_response.json()

                if response.status == 404:
                    _LOGGER.warning("Endpoint not found: %s", endpoint)
                    return {}

                response.raise_for_status()
                return await response.json()

        except (TimeoutError, aiohttp.ClientError) as e:
            _LOGGER.error("HTTP Error: %s", e)
            if _retry_count == 0:
                raise ApiError(f"HTTP Error: {e}")

            _LOGGER.debug("Retrying async request")
            return await self._authenticated_request(
                method, endpoint, data, json, _retry_count - 1
            )

    async def request(self, endpoint: str, data=None) -> dict | list:
        """Async request method."""
        target_url = BASE_URL + endpoint
        return await self._authenticated_request("GET", target_url, json=data)

    # ASYNC METHODS (Core implementation)
    async def get_account(self) -> Account:
        account_json = await self.request(Account.Request().build_url())
        return Account.model_validate(account_json)

    async def get_preferences(self) -> Preferences | None:
        """The account's preferred customer/agreement, if it has picked one."""
        account = await self.get_account()
        return account.preferences

    async def get_profiles(self) -> list[Profile]:
        return (await self.get_account()).profiles

    async def _ensure_credentials(self) -> None:
        """Fetch and cache customer_number / agreement_id if not already set."""
        if self.customer_number and self.agreement_id:
            return

        account = await self.get_account()
        # Mirror the portal: use the preferred agreement, else the first address.
        preferences = account.preferences
        if not preferences:
            profiles = account.profiles
            if not profiles:
                raise ApiError("Account has no agreement to read data for")
            preferences = Preferences(
                customer_number=profiles[0].customer_number,
                agreement_id=profiles[0].agreement_id,
            )

        self.customer_number = preferences.customer_number
        self.agreement_id = preferences.agreement_id

    async def get_meter_readings(self) -> MeterReadings:

        if not self.customer_number or not self.agreement_id:
            raise ApiError("Can not find customer_number or agreement_id for request")

        meter_json = await self.request(
            MeterReadings.Request(
                customer_number=self.customer_number,
                agreement_id=self.agreement_id,
                year=datetime.now(UTC).year,
            ).build_url(),
        )
        return MeterReadings.model_validate(meter_json)

    async def get_rates(self) -> Rates:
        if not self.customer_number or not self.agreement_id:
            raise ApiError("Can not find customer_number or agreement_id for request")

        # A range starting today returns the rates in effect today, so a
        # contract that renews later in the range doesn't shadow them.
        today = datetime.now(SUPPLIER_TZ).date()
        pricing_details = await self.request(
            Rates.Request(
                customer_number=self.customer_number,
                agreement_id=self.agreement_id,
                start=today,
                end=today + timedelta(days=1),
            ).build_url(),
        )
        return Rates.model_validate(pricing_details)

    async def get_consumptions(self, *, interval: str, start: date) -> Consumptions:
        """Fetch consumptions for a given interval and date range."""
        await self._ensure_credentials()
        if not self.customer_number or not self.agreement_id:
            raise ApiError("Can not find customer_number or agreement_id for request")

        # API only supports 1-day intervals, so end is always start + 1 day
        end = start + timedelta(days=1)

        consumptions_json = await self.request(
            Consumptions.Request(
                customer_number=self.customer_number,
                agreement_id=self.agreement_id,
                interval=interval,
                start=start,
                end=end,
            ).build_url()
        )

        return Consumptions.model_validate(consumptions_json)

    async def update(self) -> SensorUpdate:
        """Async update method."""
        result = SensorUpdate()
        try:
            await self._ensure_credentials()
        except ApiError:
            _LOGGER.error("Cant get preferences")
            return result

        try:
            await self.update_usage_values(result)
        except ApiError:
            _LOGGER.error("Cant update usage values")

        try:
            await self.update_contract_values(result)
        except ApiError:
            _LOGGER.error("Cant update contract values")

        return result

    async def update_usage_values(self, result: SensorUpdate) -> None:
        """Async usage values update."""
        _LOGGER.debug("Retrieving meter values async")
        meter_readings = await self.get_meter_readings()

        electricity_reading: Reading | None = meter_readings.last_electricity_reading
        gas_reading: Reading | None = meter_readings.last_gas_reading

        if electricity_reading:
            result.electricity_consumption_off_peak = (
                electricity_reading.off_peak_consumption
            )
            result.electricity_consumption_normal = (
                electricity_reading.normal_consumption
            )
            result.electricity_consumption_total = (
                electricity_reading.off_peak_consumption or 0
            ) + (electricity_reading.normal_consumption or 0)
            result.electricity_feed_in_off_peak = electricity_reading.off_peak_feed_in
            result.electricity_feed_in_normal = electricity_reading.normal_feed_in
            result.electricity_feed_in_total = (
                electricity_reading.off_peak_feed_in or 0
            ) + (electricity_reading.normal_feed_in or 0)
            result.electricity_reading_date = electricity_reading.reading_date

        if gas_reading:
            result.gas_consumption = gas_reading.gas
            result.gas_reading_date = gas_reading.reading_date

    async def update_contract_values(self, result: SensorUpdate) -> None:
        """Async contract values update."""
        _LOGGER.debug("Retrieving contract values async")
        try:
            pricing_details = await self.get_rates()
        except ValidationError:
            _LOGGER.warning("Could not parse the rate details response")
            return

        # The electricity field names are inferred, not verified — see
        # StandardVariableElectricityRates. Gas below is verified.
        if electricity_rates := pricing_details.electricity:
            result.electricity_price_single = _all_in_rate(
                electricity_rates.delivery_single
            )
            result.electricity_price_off_peak = _all_in_rate(
                electricity_rates.delivery_low
            )
            result.electricity_price_normal = _all_in_rate(
                electricity_rates.delivery_normal
            )
            result.electricity_feed_in_compensation = (
                electricity_rates.feed_in_compensation
            )
            if electricity_rates.feed_in_costs:
                result.electricity_feed_in_cost = (
                    electricity_rates.feed_in_costs.rate_including_vat
                )

        if gas_rates := pricing_details.gas:
            result.gas_price = _all_in_rate(gas_rates.delivery)

        if not pricing_details.electricity and not pricing_details.gas:
            # Don't let a shape change leave the price sensors silently unknown.
            _LOGGER.warning(
                "Rate details for %s..%s contain no gas and no electricity rates",
                pricing_details.start,
                pricing_details.end,
            )

    @staticmethod
    def validate_list(
        model: type[T], data: dict | list, ignore_invalid: bool = False
    ) -> list[T]:
        """Validate a list of items against a Pydantic model, optionally ignoring invalid items."""
        valid_items = []
        for item in data:
            try:
                valid_items.append(model.model_validate(item))
            except ValidationError:
                if not ignore_invalid:
                    raise
                _LOGGER.warning("Ignoring invalid item: %s", item)
        return valid_items
