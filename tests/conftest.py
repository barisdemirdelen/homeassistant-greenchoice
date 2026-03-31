import datetime
import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from aioresponses import CallbackResult, aioresponses

from custom_components.greenchoice.api import BASE_URL


@pytest.fixture
def data_folder():
    return Path(__file__).parent.joinpath("test_data")


@pytest.fixture
def contract_response(data_folder):
    with data_folder.joinpath("test_contract.json").open() as f:
        return json.load(f)


@pytest.fixture
def contract_response_without_gas(data_folder):
    with data_folder.joinpath("test_contract.json").open() as f:
        response = json.load(f)
    response["gas"] = None
    return response


@pytest.fixture
def contract_response_current(data_folder):
    with data_folder.joinpath("test_contract_current.json").open() as f:
        return json.load(f)


@pytest.fixture
def contract_response_current_without_gas(data_folder):
    with data_folder.joinpath("test_contract_current.json").open() as f:
        response = json.load(f)
    del response["contracts"][1]
    return response


@pytest.fixture
def contract_response_current_without_gas_single(data_folder):
    with data_folder.joinpath("test_contract_current.json").open() as f:
        response = json.load(f)
    del response["contracts"][1]

    rates = response["contracts"][0]["rates"]["usageDependentElectricityRates"]
    rates["allInDeliveryLowIncludingVat"] = None
    rates["deliveryLow"] = None
    rates["allInDeliveryLowVat"] = None
    rates["allInDeliveryNormalIncludingVat"] = None
    rates["deliveryNormal"] = None
    rates["allInDeliveryNormalVat"] = None
    return response


@pytest.fixture
def meters_response(data_folder):
    with data_folder.joinpath("test_meters.json").open() as f:
        return json.load(f)


@pytest.fixture
def meters_response_without_gas(data_folder):
    with data_folder.joinpath("test_meters.json").open() as f:
        response = json.load(f)
    del response["aansluitingGegevens"][1]
    return response


@pytest.fixture
def meters_v2_response(data_folder):
    with data_folder.joinpath("test_meters_v2.json").open() as f:
        return json.load(f)


@pytest.fixture
def meters_v2_response_without_gas(data_folder):
    with data_folder.joinpath("test_meters_v2.json").open() as f:
        response = json.load(f)
    del response[1]
    return response


@pytest.fixture
def init_response(data_folder):
    with data_folder.joinpath("test_init.json").open() as f:
        return json.load(f)


@pytest.fixture
def profiles_response(data_folder):
    with data_folder.joinpath("test_profiles.json").open() as f:
        return json.load(f)


@pytest.fixture
def preferences_response(data_folder):
    with data_folder.joinpath("test_preferences.json").open() as f:
        return json.load(f)


@pytest.fixture
def tariffs_v1_response(data_folder):
    with data_folder.joinpath("test_tariffs_v1.json").open() as f:
        return json.load(f)


@pytest.fixture
def init_response_without_gas(data_folder):
    with data_folder.joinpath("test_init.json").open() as f:
        response = json.load(f)
    del response["klantgegevens"][0]["adressen"][0]["contracten"][1]
    return response


@pytest.fixture
def contract_response_callback(contract_response, contract_response_without_gas):
    def _contract_response_callback(url, **kwargs):
        parsed = urlparse(str(url))
        query_params = parse_qs(parsed.query)
        qs = {k: v for k, v in query_params.items()}

        if qs == {
            "agreementidelectricity": ["1111"],
            "agreementidgas": ["1111"],
            "housenumber": ["1"],
            "referenceidelectricity": ["12345"],
            "referenceidgas": ["54321"],
            "zipcode": ["1234ab"],
        }:
            return contract_response

        if qs == {
            "agreementidelectricity": ["1111"],
            "housenumber": ["1"],
            "referenceidelectricity": ["12345"],
            "zipcode": ["1234ab"],
        }:
            return contract_response_without_gas

        return {"status": 400}

    return _contract_response_callback


@pytest.fixture
def consumptions_hour_response(data_folder):
    with data_folder.joinpath("test_consumptions_hour.json").open() as f:
        return json.load(f)


@pytest.fixture
def mock_api(
    mocker,
    init_response,
    meters_response,
    meters_v2_response,
    profiles_response,
    preferences_response,
    tariffs_v1_response,
    contract_response_callback,
    contract_response_current,
    contract_response_current_without_gas,
    contract_response_current_without_gas_single,
    init_response_without_gas,
    meters_response_without_gas,
    meters_v2_response_without_gas,
):
    with aioresponses() as mocked:

        def _mock_api(
            has_gas: bool = True,
            has_rates: bool = True,
            has_profiles: bool = True,
            double_rate: bool = True,
            consumptions: dict | None = None,
        ):
            mocker.patch(
                "custom_components.greenchoice.auth.Auth.refresh_session",
                return_value=None,
            )

            mocked.get(
                f"{BASE_URL}/microbus/init",
                payload=init_response if has_gas else init_response_without_gas,
            )

            mocked.post(
                f"{BASE_URL}/microbus/request",
                payload=meters_response if has_gas else meters_response_without_gas,
            )

            mocked.get(f"{BASE_URL}/api/tariffs", payload=tariffs_v1_response)

            if has_rates:
                mocked.get(
                    f"{BASE_URL}/api/v2/customers/2222/rates",
                    callback=lambda url, **kwargs: contract_response_callback(
                        url, **kwargs
                    ),
                )
            else:
                mocked.get(
                    f"{BASE_URL}/api/v2/customers/2222/rates",
                    payload={"status": 404},
                    status=404,
                )

            if has_profiles:
                mocked.get(
                    f"{BASE_URL}/api/v2/Profiles/",
                    payload=profiles_response,
                )
            else:
                mocked.get(f"{BASE_URL}/api/v2/Profiles/", payload=[])

            mocked.get(
                f"{BASE_URL}/api/v2/Preferences/",
                payload=preferences_response,
            )

            mocked.get(
                (
                    f"{BASE_URL}/api/v2/customers/2222/agreements/1111/meter-readings/"
                    f"{datetime.datetime.now(datetime.UTC).year}/"
                ),
                payload=meters_v2_response
                if has_gas
                else meters_v2_response_without_gas,
            )

            if has_rates:
                payload = contract_response_current
                if not has_gas:
                    payload = contract_response_current_without_gas
                if not has_gas and not double_rate:
                    payload = contract_response_current_without_gas_single
                mocked.get(
                    f"{BASE_URL}/api/v2/customers/2222/agreements/1111/contracts/current",
                    payload=payload,
                )
            else:
                mocked.get(
                    f"{BASE_URL}/api/v2/customers/2222/agreements/1111/contracts/current",
                    payload={"status": 404},
                    status=404,
                )

            # Optional: mock hourly consumptions endpoint.
            # consumptions is a dict of {date_str: payload}, e.g. {"2026-03-27": {...}}.
            # Any date not in the dict automatically returns an empty consumptions
            # response, so tests only need to list dates that should carry data.
            if consumptions is not None:
                _specific = consumptions

                def _consumptions_cb(url, **kwargs):
                    params = parse_qs(urlparse(str(url)).query)
                    start = params.get("start", ["2000-01-01"])[0]
                    end = params.get("end", ["2000-01-02"])[0]
                    if start in _specific:
                        return CallbackResult(payload=_specific[start])
                    return CallbackResult(
                        payload={
                            "interval": "Hour",
                            "start": f"{start}T00:00:00",
                            "end": f"{end}T00:00:00",
                            "consumptionCosts": [],
                        }
                    )

                mocked.get(
                    re.compile(
                        re.escape(BASE_URL)
                        + r"/api/v2/customers/\d+/agreements/\d+/consumptions"
                    ),
                    callback=_consumptions_cb,
                    repeat=True,
                )

            return mocked

        yield _mock_api


@pytest.fixture
def mock_import_statistics():
    """Patch async_import_statistics in hourly_statistics for the duration of the test."""
    with patch(
        "custom_components.greenchoice.hourly_statistics.async_import_statistics",
        new=Mock(),
    ) as m:
        yield m


@pytest.fixture
def patch_hourly_now():
    """Factory: returns a context manager that patches dt_util.now in hourly_statistics."""

    def _patch(return_value):
        return patch(
            "custom_components.greenchoice.hourly_statistics.dt_util.now",
            return_value=return_value,
        )

    return _patch


@pytest.fixture
def patch_recorder_days():
    """Factory: returns a context manager that patches _get_days_with_data.

    Pass one dict  → that dict is returned for every call (return_value).
    Pass two dicts → they are returned in order (side_effect), which is needed when
                     the function calls _get_days_with_data separately for consumption
                     and feed-in statistic IDs.
    """

    def _patch(*return_values):
        mock = (
            AsyncMock(return_value=return_values[0])
            if len(return_values) == 1
            else AsyncMock(side_effect=list(return_values))
        )
        return patch(
            "custom_components.greenchoice.hourly_statistics._get_days_with_data",
            new=mock,
        )

    return _patch
