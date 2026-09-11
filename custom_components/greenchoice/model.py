from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from datetime import date, datetime
from typing import NamedTuple

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator
from pydantic.alias_generators import to_camel

_LOGGER = logging.getLogger(__name__)


class CamelCaseModel(BaseModel):
    # populate_by_name lets these models also be built from field names,
    # not just the camelCase aliases the API sends.
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Profile(CamelCaseModel):
    """/api/v2/profiles"""

    customer_number: int
    agreement_id: int
    role_name: str | None = None
    name: str | None = None
    street: str | None = None
    house_number: int | None = None
    house_number_addition: int | str | None = None
    postal_code: str | None = None
    city: str | None = None
    energy_supply_status: str | None = None
    move_in_date: datetime | None = None
    has_active_gas_supply: bool | None = None
    has_active_electricity_supply: bool | None = None
    move_out_date: datetime | None = None


class Preferences(CamelCaseModel):
    """The customer/agreement pair the account last selected, from /api/v2/account."""

    customer_number: int
    agreement_id: int


class AccountAgreement(CamelCaseModel):
    """One (sub)agreement on an address inside /api/v2/account."""

    agreement_id: int | None = None
    sub_agreement_id: int | None = None
    name: str | None = None
    market_segment: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    duration_in_months: int | None = None
    is_variable: bool | None = None
    is_revocable: bool | None = None
    rate_structure_type: str | None = None


class EndedSupply(NamedTuple):
    """An energy supply the account reports as finished.

    ``on`` is the day it ended, or ``None`` when the account says the supply
    is over but not when — the distinction matters only to the log message.
    """

    on: date | None


class AccountAddress(CamelCaseModel):
    """One delivery address inside /api/v2/account."""

    customer_number: int | None = None
    agreement_id: int | None = None
    street: str | None = None
    house_number: int | None = None
    addition: int | str | None = None
    postal_code: str | None = None
    city: str | None = None
    move_in_date: datetime | None = None
    move_out_date: datetime | None = None
    has_gas_supply: bool | None = None
    has_electricity_supply: bool | None = None
    has_feed_in: bool | None = None
    energy_supply_status: str | None = None
    agreements: list[AccountAgreement] = []

    def ended_supply(self, day: date) -> EndedSupply | None:
        """This address's supply if it had finished by ``day``, else ``None``.

        Either signal is enough: the account calling the supply "Past", or a
        move-out / agreement end date on or before ``day``. A "Past" address
        with no dates at all still counts as ended — it just cannot say when.

        Greenchoice only serves rates for dates inside an agreement period, so
        this is what separates "your contract ended" from "the API changed".
        """
        candidates = [self.move_out_date.date()] if self.move_out_date else []
        candidates += [a.end_date for a in self.agreements if a.end_date]
        # Latest end wins: the agreements list carries the address's whole
        # history, and only the final one explains today's missing rates.
        past = max((c for c in candidates if c <= day), default=None)

        if self.energy_supply_status == "Past" or past:
            return EndedSupply(on=past)
        return None


class AccountCustomer(CamelCaseModel):
    """One customer inside /api/v2/account."""

    customer_number: int
    full_name: str | None = None
    given_name: str | None = None
    surname: str | None = None
    email: str | None = None
    status: str | None = None
    customer_type: str | None = None
    role: str | None = None
    addresses: list[AccountAddress] = []


class Account(CamelCaseModel):
    """/api/v2/account

    Replaces the removed ``/api/v2/Preferences/`` (now PUT-only) and
    ``/api/v2/Profiles/`` (now ``/api/v2/profiles/search``) endpoints: this one
    response carries both the preferred customer/agreement and the full list of
    addresses to choose from.
    """

    account_id: uuid.UUID
    email: str | None = None
    account_type: str | None = None
    first_name: str | None = None
    preferences: Preferences | None = None
    customers: list[AccountCustomer] = []

    class Request(BaseModel):
        request_url: str = "/api/v2/account"

        def build_url(self) -> str:
            return self.request_url

    def _resolved_addresses(
        self,
    ) -> Iterator[tuple[int, AccountCustomer, AccountAddress]]:
        """Every address with the customer it hangs off and the number it is polled under.

        An address carries its own customer number, but not always: fall back
        to the customer's. Both the profile list and the supply-status lookup
        depend on that rule, so it lives here once.
        """
        for customer in self.customers:
            for address in customer.addresses:
                yield (
                    address.customer_number or customer.customer_number,
                    customer,
                    address,
                )

    def ended_supply(self, preferences: Preferences, day: date) -> EndedSupply | None:
        """The polled agreement's supply if it had finished by ``day``, else ``None``."""
        address = next(
            (
                address
                for customer_number, _, address in self._resolved_addresses()
                if customer_number == preferences.customer_number
                and address.agreement_id == preferences.agreement_id
            ),
            None,
        )
        return address.ended_supply(day) if address else None

    @property
    def profiles(self) -> list[Profile]:
        """Flatten customers/addresses into the profiles the config flow lists."""
        return [
            Profile(
                customer_number=customer_number,
                agreement_id=address.agreement_id,
                role_name=customer.role,
                name=customer.full_name,
                street=address.street,
                house_number=address.house_number,
                house_number_addition=address.addition,
                postal_code=address.postal_code,
                city=address.city,
                energy_supply_status=address.energy_supply_status,
                move_in_date=address.move_in_date,
                move_out_date=address.move_out_date,
                has_active_gas_supply=address.has_gas_supply,
                has_active_electricity_supply=address.has_electricity_supply,
            )
            for customer_number, customer, address in self._resolved_addresses()
            # An address without an agreement can't be polled, so don't offer it.
            if address.agreement_id
        ]


class RateAmount(CamelCaseModel):
    """A single rate with its energy-tax/VAT breakdown.

    ``all_in_rate_including_vat`` is delivery + energy tax + VAT — the number the
    Greenchoice portal shows as the headline tariff, and what the price sensors
    report.

    VERIFIED against a live gas response: the value here matched the portal's
    displayed gas tariff exactly.
    """

    energy_tax: float | None = None
    all_in_rate_excluding_vat: float | None = None
    all_in_rate_vat: float | None = None
    all_in_rate_including_vat: float | None = None
    vat_percentage: float | None = None
    vat: float | None = None
    rate_excluding_vat: float | None = None
    rate_including_vat: float | None = None


class StandardVariableElectricityRates(CamelCaseModel):
    """Electricity rates for a Standard (non time-of-use) contract.

    VERIFIED against a live in-contract response (see the live rate-details
    test fixture). These names were originally read off the Greenchoice
    portal's frontend, because the development account had no electricity
    contract and returned ``electricityRates: null`` every time; a later
    capture for a date inside the contract confirmed both guesses:
      * ``feed_in_compensation`` really is a bare number, not a nested rate
        object.
      * the three delivery rates really are nested objects, read via
        ``all_in_rate_including_vat`` like gas.

    ``feed_in_costs`` may legitimately be ``null``. If the shape changes again
    the electricity sensors stay ``None`` and a warning names the field; gas is
    unaffected (see ``Rates._ignore_unparseable_field``).
    """

    delivery_single: RateAmount | None = None
    delivery_normal: RateAmount | None = None
    delivery_low: RateAmount | None = None
    feed_in_compensation: float | None = None
    feed_in_costs: RateAmount | None = None


class ElectricityRates(CamelCaseModel):
    """Electricity section of /rate-details.

    NOT IMPLEMENTED: time-of-use contracts report per-time-slot rates under
    ``timeOfUseVariableRates`` instead. There is no single value the current
    price sensors could hold, so it is deliberately left unmapped — such an
    account gets the "no gas and no electricity rates" warning rather than a
    wrong number.
    """

    standard_variable_rates: StandardVariableElectricityRates | None = None


class GasVariableRates(CamelCaseModel):
    """Gas rates. VERIFIED against a live response."""

    delivery: RateAmount | None = None


class GasRates(CamelCaseModel):
    """Gas section of /rate-details."""

    variable_rates: GasVariableRates | None = None


class Rates(CamelCaseModel):
    """/api/v3/customers/{customer_number}/agreements/{agreement_id}/rate-details

    Replaces the removed v2 ``/contracts/current``. The v3 ``/contracts/current``
    also exists but carries only bare delivery rates (no feed-in), so the rate
    details are what the sensors are built from.
    """

    start: date | None = None
    end: date | None = None
    electricity_rates: ElectricityRates | None = None
    gas_rates: GasRates | None = None

    @field_validator("start", "end", "electricity_rates", "gas_rates", mode="wrap")
    @classmethod
    def _ignore_unparseable_field(cls, value, handler, info):
        """Keep one field's shape change from blanking the rest of the response.

        Gas and electricity are independent sections of the same response, so
        validating them together would let an unexpected electricity shape
        discard a perfectly good gas rate, and the other way round. start/end
        only label log messages, so they must never cost us a rate either.
        """
        try:
            return handler(value)
        except ValidationError as err:
            _LOGGER.warning("Ignoring unparseable %s: %s", info.field_name, err)
            return None

    class Request(BaseModel):
        request_url: str = (
            "/api/v3/customers/{customer_number}/agreements/{agreement_id}/rate-details"
        )

        customer_number: int
        agreement_id: int
        start: date
        end: date

        def build_url(self) -> str:
            # Greenchoice expects capitalised Start/End dates (YYYY-MM-DD) here.
            return (
                self.request_url.format(
                    customer_number=self.customer_number,
                    agreement_id=self.agreement_id,
                )
                + f"?Start={self.start.isoformat()}&End={self.end.isoformat()}"
            )

    @property
    def electricity(self) -> StandardVariableElectricityRates | None:
        if self.electricity_rates:
            return self.electricity_rates.standard_variable_rates
        return None

    @property
    def gas(self) -> GasVariableRates | None:
        if self.gas_rates:
            return self.gas_rates.variable_rates
        return None


class Reading(CamelCaseModel):
    reading_date: datetime
    normal_consumption: float | None = None
    off_peak_consumption: float | None = None
    normal_feed_in: float | None = None
    off_peak_feed_in: float | None = None
    gas: float | None = None

    @property
    def is_gas(self) -> bool:
        return self.gas is not None


class MeterMonth(BaseModel):
    month: int
    readings: list[Reading]


class MeterReadings(CamelCaseModel):
    year: int
    has_electricity: bool
    has_gas: bool
    months: list[MeterMonth]

    class Request(BaseModel):
        request_url: str = """/api/v2/customers/{customer_number}/agreements/{agreement_id}/meter-readings/{year}/"""

        customer_number: int
        agreement_id: int
        year: int

        def build_url(self) -> str:
            return self.request_url.format(
                customer_number=self.customer_number,
                agreement_id=self.agreement_id,
                year=self.year,
            )

    @property
    def last_electricity_reading(self) -> Reading | None:
        for last_reading in self.iter_readings(is_gas=False):
            return last_reading
        return None

    @property
    def last_gas_reading(self) -> Reading | None:
        for last_reading in self.iter_readings(is_gas=True):
            return last_reading
        return None

    def iter_readings(self, is_gas: bool) -> Iterator[Reading]:
        readings = [
            reading
            for month in self.months
            for reading in month.readings
            if reading.is_gas == is_gas
        ]
        yield from sorted(readings, key=lambda r: r.reading_date, reverse=True)


class SensorUpdate(BaseModel):
    electricity_consumption_off_peak: float | None = None
    electricity_consumption_normal: float | None = None
    electricity_consumption_total: float | None = None
    electricity_feed_in_off_peak: float | None = None
    electricity_feed_in_normal: float | None = None
    electricity_feed_in_total: float | None = None
    electricity_reading_date: datetime | None = None

    electricity_price_single: float | None = None
    electricity_price_off_peak: float | None = None
    electricity_price_normal: float | None = None
    electricity_feed_in_compensation: float | None = None
    electricity_feed_in_cost: float | None = None

    gas_consumption: float | None = None
    gas_reading_date: datetime | None = None
    gas_price: float | None = None


class ConsumptionCostsElectricity(CamelCaseModel):
    """Electricity details inside /consumptions response."""

    delivery_low_consumption: float | None = None
    delivery_low_costs: float | None = None
    delivery_normal_consumption: float | None = None
    delivery_normal_costs: float | None = None
    feed_in_low_consumption: float | None = None
    feed_in_low_compensation: float | None = None
    feed_in_normal_consumption: float | None = None
    feed_in_normal_compensation: float | None = None
    variable_feed_in_costs: float | None = None
    fixed_delivery_costs: float | None = None
    grid_operator_costs: float | None = None
    reduction_energy_tax: float | None = None

    total_delivery_consumption: float | None = None
    total_delivery_costs: float | None = None
    total_feed_in_consumption: float | None = None
    total_feed_in_compensation: float | None = None
    total_feed_in_costs: float | None = None
    total_fixed_costs: float | None = None
    has_consumption: bool | None = None


class ConsumptionCostsGas(CamelCaseModel):
    """Gas details inside /consumptions response."""

    delivery_consumption: float | None = None
    delivery_costs: float | None = None
    fixed_delivery_costs: float | None = None
    grid_operator_costs: float | None = None

    total_delivery_consumption: float | None = None
    total_delivery_costs: float | None = None
    total_fixed_costs: float | None = None
    has_consumption: bool | None = None


class ConsumptionCostsNet(CamelCaseModel):
    """Net electricity/cost summary inside /consumptions response."""

    net_electricity_consumption: float | None = None
    net_electricity_costs: float | None = None
    net_costs: float | None = None


class ConsumptionCostsItem(CamelCaseModel):
    """An hourly consumptionCosts item."""

    consumed_on: datetime
    electricity: ConsumptionCostsElectricity | None = None
    gas: ConsumptionCostsGas | None = None
    net: ConsumptionCostsNet | None = None
    has_consumption: bool | None = None


class Consumptions(CamelCaseModel):
    """/api/v2/customers/{customer_number}/agreements/{agreement_id}/consumptions"""

    interval: str
    start: datetime
    end: datetime
    consumption_costs: list[ConsumptionCostsItem] = []
    total: ConsumptionCostsItem | None = None
    has_consumption: bool | None = None

    class Request(BaseModel):
        request_url: str = (
            "/api/v2/customers/{customer_number}/agreements/{agreement_id}/consumptions"
        )

        customer_number: int
        agreement_id: int
        interval: str
        start: date
        end: date

        def build_url(self) -> str:
            # Greenchoice expects dates (YYYY-MM-DD) for start/end query params.
            return (
                self.request_url.format(
                    customer_number=self.customer_number, agreement_id=self.agreement_id
                )
                + f"?interval={self.interval}&start={self.start.isoformat()}&end={self.end.isoformat()}"
            )
