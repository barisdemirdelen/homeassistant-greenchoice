import datetime
import json
from pathlib import Path

import pytest
import requests

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
    del response["productTypes"][1]
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
    def _contract_response_callback(request, context):
        if request.qs == {
            "agreementidelectricity": ["1111"],
            "agreementidgas": ["1111"],
            "housenumber": ["1"],
            "referenceidelectricity": ["12345"],
            "referenceidgas": ["54321"],
            "zipcode": ["1234ab"],
        }:
            return contract_response
        if request.qs == {
            "agreementidelectricity": ["1111"],
            "housenumber": ["1"],
            "referenceidelectricity": ["12345"],
            "zipcode": ["1234ab"],
        }:
            return contract_response_without_gas
        context.status_code = 400
        return {"status": 400}

    return _contract_response_callback


@pytest.fixture
def mock_api(
    mocker,
    requests_mock,
    init_response,
    meters_response,
    meters_v2_response,
    profiles_response,
    preferences_response,
    tariffs_v1_response,
    contract_response_callback,
    init_response_without_gas,
    meters_response_without_gas,
    meters_v2_response_without_gas,
):
    def _mock_api(has_gas: bool, has_rates: bool):
        mocker.patch(
            "custom_components.greenchoice.auth.Auth.refresh_session",
            return_value=requests.Session(),
        )

        requests_mock.get(
            f"{BASE_URL}/microbus/init",
            json=init_response if has_gas else init_response_without_gas,
        )

        requests_mock.post(
            f"{BASE_URL}/microbus/request",
            json=meters_response if has_gas else meters_response_without_gas,
        )

        requests_mock.get(f"{BASE_URL}/api/tariffs", json=tariffs_v1_response)

        if has_rates:
            requests_mock.get(
                f"{BASE_URL}/api/v2/customers/2222/rates",
                json=contract_response_callback,
            )
        else:
            requests_mock.get(
                f"{BASE_URL}/api/v2/customers/2222/rates", json={"status": 404}, status_code=404
            )

        requests_mock.get(
            f"{BASE_URL}/api/v2/Profiles/",
            json=profiles_response,
        )

        requests_mock.get(
            f"{BASE_URL}/api/v2/Preferences/",
            json=preferences_response,
        )

        requests_mock.get(
            (
                f"{BASE_URL}/api/v2/customers/2222/agreements/1111/meter-readings/"
                f"{datetime.datetime.now(datetime.UTC).year}/"
            ),
            json=meters_v2_response if has_gas else meters_v2_response_without_gas,
        )

    return _mock_api
