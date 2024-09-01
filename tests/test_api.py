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
def meters_response(data_folder):
    with data_folder.joinpath("test_meters.json").open() as f:
        return json.load(f)


@pytest.fixture
def init_response(data_folder):
    with data_folder.joinpath("test_init.json").open() as f:
        return json.load(f)


def contract_request_matcher(request):
    return "GetTariefOvereenkomst" in (request.text or "")


def meters_request_matcher(request):
    return "AansluitingGegevens" in (request.text or "")


def test_update_request(
    mocker, requests_mock, init_response, contract_response, meters_response
):
    mocker.patch(
        "custom_components.greenchoice.api.GreenchoiceApiData._activate_session",
        return_value=None,
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
        json=contract_response,
    )

    greenchoice_api = GreenchoiceApiData("fake_user", "fake_password")
    greenchoice_api.session = requests.Session()

    result = greenchoice_api.update()

    assert result == {
        "electricity_consumption_low": 60000,
        "electricity_consumption_high": 50000,
        "electricity_return_low": 6000,
        "electricity_return_high": 5000,
        "electricity_consumption_total": 110000,
        "electricity_return_total": 11000,
        "measurement_date_electricity": datetime.datetime(2022, 5, 6, 0, 0),
        "gas_consumption": 10000,
        "measurement_date_gas": datetime.datetime(2023, 5, 6, 0, 0),
        "electricity_price_single": 0.25,
        "electricity_price_low": 0.2,
        "electricity_price_high": 0.3,
        "electricity_return_price": 0.08,
        "gas_price": 0.8,
    }
