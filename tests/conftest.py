import datetime
import json
from pathlib import Path

import pytest
from aioresponses import aioresponses

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
        # Parse query parameters from URL
        from urllib.parse import urlparse, parse_qs

        parsed = urlparse(str(url))
        query_params = parse_qs(parsed.query)

        # Convert to same format as requests_mock
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
    init_response_without_gas,
    meters_response_without_gas,
    meters_v2_response_without_gas,
):
    with aioresponses() as mocked:

        def _mock_api(has_gas: bool, has_rates: bool):
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

            mocked.get(
                f"{BASE_URL}/api/v2/Profiles/",
                payload=profiles_response,
            )

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
                mocked.get(
                    f"{BASE_URL}/api/v2/customers/2222/agreements/1111/contracts/current",
                    payload=contract_response_current
                    if has_gas
                    else contract_response_current_without_gas,
                )
            else:
                mocked.get(
                    f"{BASE_URL}/api/v2/customers/2222/agreements/1111/contracts/current",
                    payload={"status": 404},
                    status=404,
                )

            return mocked

        yield _mock_api

