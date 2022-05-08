import datetime
import json
from pathlib import Path

import pytest
import requests

from custom_components.greenchoice.api import GreenchoiceApiData, BASE_URL


@pytest.fixture()
def data_folder():
    return Path(__file__).parent.joinpath("test_data")


@pytest.fixture()
def contract_response(data_folder):
    """Fixture that returns a static weather data."""
    with data_folder.joinpath("test_contract.json").open() as f:
        return json.load(f)


@pytest.fixture()
def meters_response(data_folder):
    """Fixture that returns a static weather data."""
    with data_folder.joinpath("test_meters.json").open() as f:
        return json.load(f)


def contract_request_matcher(request):
    return "GetTariefOvereenkomst" in (request.text or "")


def meters_request_matcher(request):
    return "OpnamesOphalen" in (request.text or "")


def test_update_request(mocker, requests_mock, contract_response, meters_response):
    mocker.patch(
        "custom_components.greenchoice.api.GreenchoiceApiData._activate_session",
        return_value=None,
    )

    mock_address = f"{BASE_URL}/microbus/request"
    requests_mock.post(
        mock_address,
        additional_matcher=contract_request_matcher,
        json=contract_response,
    )

    requests_mock.post(
        mock_address,
        additional_matcher=meters_request_matcher,
        json=meters_response,
    )

    greenchoice_api = GreenchoiceApiData("fake_user", "fake_password")
    greenchoice_api.session = requests.Session()

    result = greenchoice_api.update()

    assert result == {
        "electricity_consumption_low": 6890,
        "electricity_consumption_high": 68000,
        "electricity_return_low": 0,
        "electricity_return_high": 0,
        "electricity_consumption_total": 74890,
        "electricity_return_total": 0,
        "measurement_date_electricity": datetime.datetime(2021, 11, 17, 0, 0),
        "gas_consumption": 50000,
        "measurement_date_gas": datetime.datetime(2022, 5, 6, 0, 0),
        "electricity_price_single": 0.25,
        "electricity_price_low": 0.2,
        "electricity_price_high": 0.3,
        "electricity_return_price": 0.08,
        "gas_price": 0.8,
    }
