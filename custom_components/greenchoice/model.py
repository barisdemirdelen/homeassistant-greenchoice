import uuid
from datetime import datetime

from pydantic import BaseModel

import typing as t


class Profile(BaseModel):
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
    hasActiveGasSupply: bool
    hasActiveElectricitySupply: bool


class PreferencesSubject(BaseModel):
    customerNumber: int
    LeveringsStatus: int
    agreementId: int


class Preferences(BaseModel):
    """/api/v2/preferences"""

    accountId: uuid.UUID
    subject: PreferencesSubject


class Account(BaseModel):
    """/api/v2/accounts"""

    accountId: uuid.UUID
    email: str
    emailModifiedOnUtc: datetime
    accountType: str
    accountTypeModifiedOnUtc: datetime
    firstName: str
    accountTypeModifiedOnUtc: datetime


class ElectricityTariff(BaseModel):
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
    rebTeruggaveIncBtw: float | None = None
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


class GasTariff(BaseModel):
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


class Rates(BaseModel):
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


class Reading(BaseModel):
    readingDate: datetime
    normalConsumption: float | None
    offPeakConsumption: float | None
    normalFeedIn: float | None
    offPeakFeedIn: float | None
    gas: float | None


class MeterMonth(BaseModel):
    month: int
    readings: list[Reading]


class MeterProduct(BaseModel):
    productType: str
    months: list[MeterMonth]


class MeterReadings(BaseModel):
    """/api/v2/MeterReadings/<year>/<customerNumber>/<agreementId>"""

    productTypes: list[MeterProduct]
