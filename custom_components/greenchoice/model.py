from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Iterator


@dataclass
class Profile:
    """/api/v2/profiles"""

    customerNumber: int
    agreementId: int
    roleName: str
    name: str
    street: str
    houseNumber: int
    houseNumberAddition: int | str | None
    postalCode: str
    city: str
    energySupplyStatus: str
    moveInDate: datetime
    moveOutDate: datetime | None
    hasActiveGasSupply: bool
    hasActiveElectricitySupply: bool

    @staticmethod
    def from_dict(data: dict) -> Profile:
        return Profile(
            customerNumber=data.get("customerNumber"),
            agreementId=data.get("agreementId"),
            roleName=data.get("roleName"),
            name=data.get("name"),
            street=data.get("street"),
            houseNumber=data.get("houseNumber"),
            houseNumberAddition=data.get("houseNumberAddition"),
            postalCode=data.get("postalCode"),
            city=data.get("city"),
            energySupplyStatus=data.get("energySupplyStatus"),
            moveInDate=data.get("moveInDate"),
            moveOutDate=data.get("moveOutDate"),
            hasActiveGasSupply=data.get("hasActiveGasSupply"),
            hasActiveElectricitySupply=data.get("hasActiveElectricitySupply"),
        )


@dataclass
class PreferencesSubject:
    customerNumber: int
    LeveringsStatus: int
    agreementId: int

    @staticmethod
    def from_dict(data: dict) -> PreferencesSubject:
        return PreferencesSubject(
            customerNumber=data.get("customerNumber"),
            LeveringsStatus=data.get("LeveringsStatus"),
            agreementId=data.get("agreementId"),
        )


@dataclass
class Preferences:
    """/api/v2/preferences"""

    accountId: uuid.UUID
    subject: PreferencesSubject

    @staticmethod
    def from_dict(data: dict) -> Preferences:
        return Preferences(
            accountId=uuid.UUID(data.get("accountId")),
            subject=PreferencesSubject.from_dict(data.get("subject")),
        )


@dataclass
class Account:
    """/api/v2/accounts"""

    accountId: uuid.UUID
    email: str
    accountType: str
    firstName: str
    emailModifiedOnUtc: datetime
    accountTypeModifiedOnUtc: datetime
    firstNameModifiedOnUtc: datetime

    @staticmethod
    def from_dict(data: dict) -> Account:
        return Account(
            accountId=uuid.UUID(data.get("accountId")),
            email=data.get("email"),
            accountType=data.get("accountType"),
            firstName=data.get("firstName"),
            emailModifiedOnUtc=datetime.fromisoformat(data.get("emailModifiedOnUtc")),
            accountTypeModifiedOnUtc=datetime.fromisoformat(
                data.get("accountTypeModifiedOnUtc")
            ),
            firstNameModifiedOnUtc=datetime.fromisoformat(
                data.get("firstNameModifiedOnUtc")
            ),
        )


@dataclass
class ElectricityTariff:
    leveringHoog: float
    leveringLaag: float
    leveringEnkel: float
    leveringLaagAllIn: float
    leveringHoogAllIn: float
    leveringEnkelAllIn: float
    leveringHoogBtw: float
    leveringLaagBtw: float
    leveringEnkelBtw: float
    soortMeter: str
    terugLeveringEnkel: float
    terugLeveringHoog: float
    terugLeveringLaag: float
    terugleverVergoeding: float
    terugleverKostenIncBtw: float
    terugleverKostenExcBtw: float
    terugleverKostenBtw: float
    btw: float
    btwPercentage: float
    vastrechtPerDagExcBtw: float
    vastrechtPerDagIncBtw: float
    vastrechtPerDagBtw: float
    netbeheerPerDagExcBtw: float
    netbeheerPerDagIncBtw: float
    netbeheerPerDagBtw: float
    reb: float
    sde: float
    capaciteit: str | None
    rebTeruggaveIncBtw: float | None

    @staticmethod
    def from_dict(data: dict) -> ElectricityTariff:
        return ElectricityTariff(
            leveringHoog=data.get("leveringHoog"),
            leveringLaag=data.get("leveringLaag"),
            leveringEnkel=data.get("leveringEnkel"),
            leveringLaagAllIn=data.get("leveringLaagAllIn")
            or data.get("leveringLaagAllin"),
            leveringHoogAllIn=data.get("leveringHoogAllIn")
            or data.get("leveringHoogAllin"),
            leveringEnkelAllIn=data.get("leveringEnkelAllIn")
            or data.get("leveringEnkelAllin"),
            leveringHoogBtw=data.get("leveringHoogBtw"),
            leveringLaagBtw=data.get("leveringLaagBtw"),
            leveringEnkelBtw=data.get("leveringEnkelBtw"),
            soortMeter=data.get("soortMeter"),
            terugLeveringEnkel=data.get("terugLeveringEnkel"),
            terugLeveringHoog=data.get("terugLeveringHoog"),
            terugLeveringLaag=data.get("terugLeveringLaag"),
            terugleverVergoeding=data.get("terugleverVergoeding"),
            terugleverKostenIncBtw=data.get("terugleverKostenIncBtw"),
            terugleverKostenExcBtw=data.get("terugleverKostenExcBtw"),
            terugleverKostenBtw=data.get("terugleverKostenBtw"),
            btw=data.get("btw"),
            btwPercentage=data.get("btwPercentage"),
            vastrechtPerDagExcBtw=data.get("vastrechtPerDagExcBtw"),
            vastrechtPerDagIncBtw=data.get("vastrechtPerDagIncBtw"),
            vastrechtPerDagBtw=data.get("vastrechtPerDagBtw"),
            netbeheerPerDagExcBtw=data.get("netbeheerPerDagExcBtw"),
            netbeheerPerDagIncBtw=data.get("netbeheerPerDagIncBtw"),
            netbeheerPerDagBtw=data.get("netbeheerPerDagBtw"),
            reb=data.get("reb"),
            sde=data.get("sde"),
            capaciteit=data.get("capaciteit"),
            rebTeruggaveIncBtw=data.get("rebTeruggaveIncBtw"),
        )


@dataclass
class GasTariff:
    levering: float
    leveringAllIn: float
    leveringBtw: float
    btw: float
    btwPercentage: float
    vastrechtPerDagExcBtw: float
    vastrechtPerDagIncBtw: float
    vastrechtPerDagBtw: float
    netbeheerPerDagExcBtw: float
    netbeheerPerDagIncBtw: float
    netbeheerPerDagBtw: float
    reb: float
    sde: float
    capaciteit: str | None

    @staticmethod
    def from_dict(data: dict) -> GasTariff:
        return GasTariff(
            levering=data.get("levering"),
            leveringAllIn=data.get("leveringAllIn"),
            leveringBtw=data.get("leveringBtw"),
            btw=data.get("btw"),
            btwPercentage=data.get("btwPercentage"),
            vastrechtPerDagExcBtw=data.get("vastrechtPerDagExcBtw"),
            vastrechtPerDagIncBtw=data.get("vastrechtPerDagIncBtw"),
            vastrechtPerDagBtw=data.get("vastrechtPerDagBtw"),
            netbeheerPerDagExcBtw=data.get("netbeheerPerDagExcBtw"),
            netbeheerPerDagIncBtw=data.get("netbeheerPerDagIncBtw"),
            netbeheerPerDagBtw=data.get("netbeheerPerDagBtw"),
            reb=data.get("reb"),
            sde=data.get("sde"),
            capaciteit=data.get("capaciteit"),
        )


@dataclass
class Rates:
    """/api/v2/Rates/<customerNumber>
    ?AgreementIdElectricity=<agreementId>
    &AgreementIdGas=<agreementId>
    &HouseNumber=<houseNumber>
    &ReferenceIdElectricity=<refIdElectricity>
    &ReferenceIdGas=<refIdGas>
    &ZipCode=<zipCode>>"""

    beginDatum: datetime
    eindDatum: datetime

    stroom: ElectricityTariff | None
    gas: GasTariff | None

    @staticmethod
    def from_dict(data: dict) -> Rates:
        return Rates(
            beginDatum=datetime.fromisoformat(data.get("beginDatum")),
            eindDatum=datetime.fromisoformat(data.get("eindDatum")),
            stroom=(
                ElectricityTariff.from_dict(data.get("stroom"))
                if data.get("stroom")
                else None
            ),
            gas=GasTariff.from_dict(data.get("gas")) if data.get("gas") else None,
        )


@dataclass
class Reading:
    readingDate: datetime
    normalConsumption: float | None
    offPeakConsumption: float | None
    normalFeedIn: float | None
    offPeakFeedIn: float | None
    gas: float | None

    @staticmethod
    def from_dict(data: dict) -> Reading:
        return Reading(
            readingDate=datetime.fromisoformat(data.get("readingDate")),
            normalConsumption=data.get("normalConsumption"),
            offPeakConsumption=data.get("offPeakConsumption"),
            normalFeedIn=data.get("normalFeedIn"),
            offPeakFeedIn=data.get("offPeakFeedIn"),
            gas=data.get("gas"),
        )


@dataclass
class MeterMonth:
    month: int
    readings: list[Reading]

    @staticmethod
    def from_dict(data: dict) -> MeterMonth:
        return MeterMonth(
            month=data.get("month"),
            readings=[Reading.from_dict(r) for r in data.get("readings")],
        )


@dataclass
class MeterProduct:
    productType: str
    months: list[MeterMonth]

    @staticmethod
    def from_dict(data: dict) -> MeterProduct:
        return MeterProduct(
            productType=data.get("productType"),
            months=[MeterMonth.from_dict(r) for r in data.get("months")],
        )


@dataclass
class MeterReadings:
    """/api/v2/customers/<customerNumber>/agreements/<agreementId>/meter-readings/<year>/"""

    productTypes: list[MeterProduct]

    @staticmethod
    def from_dict(data: dict) -> MeterReadings:
        return MeterReadings(
            productTypes=[MeterProduct.from_dict(r) for r in data.get("productTypes")],
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
        for product in self.productTypes:
            if product.productType.lower() != product_type:
                continue
            for month in sorted(product.months, key=lambda p: p.month, reverse=True):
                for reading in sorted(
                    month.readings, key=lambda r: r.readingDate, reverse=True
                ):
                    yield reading
