import datetime
import json
from pathlib import Path

import pytest
import requests

from custom_components.greenchoice.api import GreenchoiceApiData, BASE_URL


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


def contract_request_matcher(request):
    return "GetTariefOvereenkomst" in (request.text or "")


def meters_request_matcher(request):
    return "AansluitingGegevens" in (request.text or "")


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


def test_update_request(
    mocker,
    requests_mock,
    init_response,
    meters_response,
    meters_v2_response,
    profiles_response,
    preferences_response,
    contract_response_callback,
):
    mocker.patch(
        "custom_components.greenchoice.auth.Auth.refresh_session",
        return_value=requests.Session(),
    )

    requests_mock.get(
        f"{BASE_URL}/microbus/init",
        json=init_response,
    )

    requests_mock.post(
        f"{BASE_URL}/microbus/request",
        json=meters_response,
    )

    requests_mock.get(
        f"{BASE_URL}/api/v2/Rates/2222",
        json=contract_response_callback,
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
            f"{BASE_URL}/api/v2/MeterReadings/"
            f"{datetime.datetime.now(datetime.UTC).year}/2222/1111"
        ),
        json=meters_v2_response,
    )

    greenchoice_api = GreenchoiceApiData("fake_user", "fake_password")
    greenchoice_api.session = requests.Session()

    result = greenchoice_api.update()

    assert result == {
        "electricity_consumption_low": 60000.0,
        "electricity_consumption_high": 50000.0,
        "electricity_return_low": 6000.0,
        "electricity_return_high": 5000.0,
        "electricity_consumption_total": 110000.0,
        "electricity_return_total": 11000.0,
        "measurement_date_electricity": datetime.datetime(2022, 5, 6, 0, 0),
        "gas_consumption": 10000.0,
        "measurement_date_gas": datetime.datetime(2022, 5, 6, 0, 0),
        "electricity_price_single": 0.25,
        "electricity_price_low": 0.2,
        "electricity_price_high": 0.3,
        "electricity_return_price": 0.08,
        "gas_price": 0.8,
    }


def test_update_request_without_gas(
    mocker,
    requests_mock,
    init_response_without_gas,
    meters_response_without_gas,
    profiles_response,
    meters_v2_response_without_gas,
    preferences_response,
    contract_response_callback,
):
    mocker.patch(
        "custom_components.greenchoice.auth.Auth.refresh_session",
        return_value=requests.Session(),
    )

    requests_mock.get(
        f"{BASE_URL}/microbus/init",
        json=init_response_without_gas,
    )

    requests_mock.post(
        f"{BASE_URL}/microbus/request",
        json=meters_response_without_gas,
    )

    requests_mock.get(
        f"{BASE_URL}/api/v2/Rates/2222",
        json=contract_response_callback,
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
        f"{BASE_URL}/api/v2/MeterReadings/{datetime.datetime.now().year}/2222/1111",
        json=meters_v2_response_without_gas,
    )

    greenchoice_api = GreenchoiceApiData("fake_user", "fake_password")
    greenchoice_api.session = requests.Session()

    result = greenchoice_api.update()

    assert result == {
        "electricity_consumption_low": 60000.0,
        "electricity_consumption_high": 50000.0,
        "electricity_return_low": 6000.0,
        "electricity_return_high": 5000.0,
        "electricity_consumption_total": 110000.0,
        "electricity_return_total": 11000.0,
        "measurement_date_electricity": datetime.datetime(2022, 5, 6, 0, 0),
        "electricity_price_single": 0.25,
        "electricity_price_low": 0.2,
        "electricity_price_high": 0.3,
        "electricity_return_price": 0.08,
    }


def test_with_old_tariffs_api(
    mocker,
    requests_mock,
    init_response,
    meters_response,
    meters_v2_response,
    profiles_response,
    preferences_response,
    tariffs_v1_response,
    contract_response_callback,
):
    mocker.patch(
        "custom_components.greenchoice.auth.Auth.refresh_session",
        return_value=requests.Session(),
    )

    requests_mock.get(
        f"{BASE_URL}/microbus/init",
        json=init_response,
    )

    requests_mock.post(
        f"{BASE_URL}/microbus/request",
        json=meters_response,
    )

    requests_mock.get(
        f"{BASE_URL}/api/v2/Rates/2222", json={"status": 404}, status_code=404
    )

    requests_mock.get(f"{BASE_URL}/api/tariffs", json=tariffs_v1_response)

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
            f"{BASE_URL}/api/v2/MeterReadings/"
            f"{datetime.datetime.now(datetime.UTC).year}/2222/1111"
        ),
        json=meters_v2_response,
    )

    greenchoice_api = GreenchoiceApiData("fake_user", "fake_password")
    greenchoice_api.session = requests.Session()

    result = greenchoice_api.update()

    assert result == {
        "electricity_consumption_low": 60000.0,
        "electricity_consumption_high": 50000.0,
        "electricity_return_low": 6000.0,
        "electricity_return_high": 5000.0,
        "electricity_consumption_total": 110000.0,
        "electricity_return_total": 11000.0,
        "measurement_date_electricity": datetime.datetime(2022, 5, 6, 0, 0),
        "gas_consumption": 10000.0,
        "measurement_date_gas": datetime.datetime(2022, 5, 6, 0, 0),
        "electricity_price_single": 0.35,
        "electricity_price_low": 0.3,
        "electricity_price_high": 0.4,
        "electricity_return_price": 0.09,
        "gas_price": 0.7,
    }
