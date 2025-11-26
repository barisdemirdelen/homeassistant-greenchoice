from __future__ import annotations

import uuid
from datetime import date, datetime
from functools import cached_property
from typing import Iterator

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelCaseModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)


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
    """/api/v2/preferences"""

    account_id: uuid.UUID
    customer_number: int
    agreement_id: int


class Account(CamelCaseModel):
    """/api/v2/accounts"""

    account_id: uuid.UUID
    email: str | None = None
    account_type: str | None = None
    first_name: str | None = None
    email_modified_on_utc: datetime | None = None
    account_type_modified_on_utc: datetime | None = None
    first_name_modified_on_utc: datetime | None = None


class UsageDependentElectricityRates(CamelCaseModel):
    all_in_delivery_single_including_vat: float
    delivery_single: float
    all_in_delivery_single_vat: float
    all_in_delivery_low_including_vat: float
    delivery_low: float
    all_in_delivery_low_vat: float
    all_in_delivery_normal_including_vat: float
    delivery_normal: float
    all_in_delivery_normal_vat: float
    energy_tax: float
    sustainable_energy_surcharge: float | None = None
    feed_in_compensation: float | None = None
    feed_in_volume_limit_in_kwh: float | None = None
    feed_in_cost_including_vat: float | None = None
    feed_in_cost_excluding_vat: float | None = None
    feed_in_cost_vat: float | None = None


class UsageDependentGasRates(CamelCaseModel):
    all_in_delivery_including_vat: float
    delivery: float
    all_in_delivery_vat: float
    energy_tax: float
    sustainable_energy_surcharge: float | None = None


class UsageIndependentRates(CamelCaseModel):
    fixed_charge_per_day_including_vat: float
    fixed_charge_per_day_excluding_vat: float
    fixed_charge_per_day_vat: float
    reduction_energy_tax_including_vat_per_day: float
    grid_operator_rate_per_day_including_vat: float
    grid_operator_rate_per_day_excluding_vat: float
    grid_operator_rate_per_day_vat: float


class ContractRates(CamelCaseModel):
    vat_percentage: float
    usage_dependent_electricity_rates: UsageDependentElectricityRates | None = None
    usage_dependent_gas_rates: UsageDependentGasRates | None = None
    usage_independent_rates: UsageIndependentRates | None = None


class Contract(CamelCaseModel):
    type: str
    display_name: str
    begin_date: date
    end_date: date | None = None
    cancellation_date: date | None = None
    duration_in_months: int | None = None
    product_type: str
    physical_capacity: str
    rates: ContractRates
    rate_type: str
    sub_agreement_id: int


class Rates(BaseModel):
    id: int
    contracts: list[Contract]

    class Request(BaseModel):
        request_url: str = "/api/v2/customers/{customer_number}/agreements/{agreement_id}/contracts/current"

        customer_number: int
        agreement_id: int

        def build_url(self) -> str:
            return self.request_url.format(
                customer_number=self.customer_number, agreement_id=self.agreement_id
            )

    @cached_property
    def electricity(self) -> Contract | None:
        for contract in self.contracts:
            if contract.product_type.upper() == "E":
                return contract
        return None

    @cached_property
    def gas(self) -> Contract | None:
        for contract in self.contracts:
            if contract.product_type.upper() == "G":
                return contract
        return None


class Reading(CamelCaseModel):
    reading_date: datetime
    normal_consumption: float | None = None
    off_peak_consumption: float | None = None
    normal_feed_in: float | None = None
    off_peak_feed_in: float | None = None
    gas: float | None = None


class MeterMonth(BaseModel):
    month: int
    readings: list[Reading]


class MeterProduct(CamelCaseModel):
    product_type: str
    months: list[MeterMonth]


class MeterReadings(BaseModel):
    product_types: list[MeterProduct]

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
        for last_reading in self.iter_readings("stroom"):
            return last_reading
        return None

    @property
    def last_gas_reading(self) -> Reading | None:
        for last_reading in self.iter_readings("gas"):
            return last_reading
        return None

    def iter_readings(self, product_type) -> Iterator[Reading]:
        for product in self.product_types:
            if product.product_type.lower() != product_type:
                continue
            for month in sorted(product.months, key=lambda p: p.month, reverse=True):
                for reading in sorted(
                    month.readings, key=lambda r: r.reading_date, reverse=True
                ):
                    yield reading


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
