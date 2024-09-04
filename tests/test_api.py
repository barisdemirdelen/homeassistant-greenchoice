import datetime

from custom_components.greenchoice.api import GreenchoiceApiData


def test_update_request(
    mock_api,
):
    mock_api(has_gas=True, has_rates=True)

    greenchoice_api = GreenchoiceApiData("fake_user", "fake_password")
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


def test_update_request_without_gas(mock_api):
    mock_api(has_gas=False, has_rates=True)

    greenchoice_api = GreenchoiceApiData("fake_user", "fake_password")
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


def test_with_old_tariffs_api(mock_api):
    mock_api(has_gas=True, has_rates=False)

    greenchoice_api = GreenchoiceApiData("fake_user", "fake_password")
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
