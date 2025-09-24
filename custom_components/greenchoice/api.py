import asyncio
import logging
from datetime import UTC, datetime

import aiohttp
from pydantic import ValidationError

from .auth import Auth
from .model import (
    MeterProduct,
    MeterReadings,
    Preferences,
    Profile,
    Rates,
    Reading,
    SensorUpdate,
)

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://mijn.greenchoice.nl"


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
                            return {}
                        retry_response.raise_for_status()
                        return await retry_response.json()

                if response.status == 404:
                    return {}

                response.raise_for_status()
                return await response.json()

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            _LOGGER.error("HTTP Error: %s", e)
            if _retry_count == 0:
                raise ApiError(f"HTTP Error: {e}")

            _LOGGER.debug("Retrying async request")
            return await self._authenticated_request(
                method, endpoint, data, json, _retry_count - 1
            )

    async def request(self, endpoint: str, data=None) -> dict:
        """Async request method."""
        target_url = BASE_URL + endpoint
        return await self._authenticated_request("GET", target_url, json=data)

    # ASYNC METHODS (Core implementation)
    async def get_preferences(self) -> Preferences:
        preferences_json = await self.request("/api/v2/Preferences/")
        return Preferences.model_validate(preferences_json)

    async def get_profiles(self) -> list[Profile]:
        profiles_json = await self.request("/api/v2/Profiles/")
        return [Profile.model_validate(p) for p in profiles_json]

    async def get_meter_readings(self) -> MeterReadings:
        meter_json = await self.request(
            MeterReadings.Request(
                customer_number=self.customer_number,
                agreement_id=self.agreement_id,
                year=datetime.now(UTC).year,
            ).build_url(),
        )
        return MeterReadings(
            product_types=[MeterProduct.model_validate(mp) for mp in meter_json]
        )

    async def get_rates(self) -> Rates:
        pricing_details = await self.request(
            Rates.Request(
                customer_number=self.customer_number,
                agreement_id=self.agreement_id,
            ).build_url(),
        )
        return Rates.model_validate(pricing_details)

    async def update(self) -> SensorUpdate:
        """Async update method."""
        result = SensorUpdate()
        if not self.customer_number or not self.agreement_id:
            try:
                preferences = await self.get_preferences()
                self.customer_number = preferences.subject.customer_number
                self.agreement_id = preferences.subject.agreement_id
            except ApiError:
                _LOGGER.error("Cant get preferences")
                return result

        try:
            await self.update_usage_values(result)
        except ApiError:
            _LOGGER.error("Cant update usage values")
            pass

        try:
            await self.update_contract_values(result)
        except ApiError:
            _LOGGER.error("Cant update contract values")
            pass

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
                electricity_reading.off_peak_consumption
                + electricity_reading.normal_consumption
            )
            result.electricity_feed_in_off_peak = electricity_reading.off_peak_feed_in
            result.electricity_feed_in_normal = electricity_reading.normal_feed_in
            result.electricity_feed_in_total = (
                electricity_reading.off_peak_feed_in
                + electricity_reading.normal_feed_in
            )
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
            return

        if pricing_details.electricity:
            electricity_usage = (
                pricing_details.electricity.rates.usage_dependent_electricity_rates
            )
            result.electricity_price_single = (
                electricity_usage.all_in_delivery_single_including_vat
            )
            result.electricity_price_off_peak = (
                electricity_usage.all_in_delivery_low_including_vat
            )
            result.electricity_price_normal = (
                electricity_usage.all_in_delivery_normal_including_vat
            )
            result.electricity_feed_in_compensation = (
                electricity_usage.feed_in_compensation
            )
            result.electricity_feed_in_cost = (
                electricity_usage.feed_in_cost_including_vat
            )

        if pricing_details.gas:
            result.gas_price = pricing_details.gas.rates.usage_dependent_gas_rates.all_in_delivery_including_vat

    # SYNC METHODS (Wrapper around async methods for backward compatibility)
    @staticmethod
    def _run_async(coro):
        """Run async method in sync context."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're already in an async context, this won't work
                # Fall back to creating a new loop in a thread
                import concurrent.futures

                def run_in_thread():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(coro)
                    finally:
                        new_loop.close()

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_in_thread)
                    return future.result()
            else:
                return loop.run_until_complete(coro)
        except RuntimeError:
            # No event loop exists
            return asyncio.run(coro)

    def sync_update(self) -> SensorUpdate:
        async def _async_update_with_context():
            async with self:
                return await self.update()

        """Sync update method (calls async implementation)."""
        self.result = self._run_async(_async_update_with_context())
        return self.result
