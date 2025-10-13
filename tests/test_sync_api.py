import datetime

from custom_components.greenchoice.api import GreenchoiceApi


def test_update_request(
    mock_api,
):
    mock_api()

    greenchoice_api = GreenchoiceApi("fake_user", "fake_password")
    result = greenchoice_api.sync_update()

    assert result.model_dump() == {
        "electricity_consumption_off_peak": 60000.0,
        "electricity_consumption_normal": 50000.0,
        "electricity_consumption_total": 110000.0,
        "electricity_feed_in_off_peak": 6000.0,
        "electricity_feed_in_normal": 5000.0,
        "electricity_feed_in_total": 11000.0,
        "electricity_reading_date": datetime.datetime(2022, 5, 6, 0, 0),
        "electricity_price_single": 0.25,
        "electricity_price_off_peak": 0.2,
        "electricity_price_normal": 0.3,
        "electricity_feed_in_compensation": 0.08,
        "electricity_feed_in_cost": 0.01,
        "gas_consumption": 10000.0,
        "gas_reading_date": datetime.datetime(2022, 5, 6, 0, 0),
        "gas_price": 0.8,
    }


def test_update_request_without_gas(mock_api):
    mock_api(has_gas=False)

    greenchoice_api = GreenchoiceApi("fake_user", "fake_password")
    result = greenchoice_api.sync_update()

    assert result.model_dump() == {
        "electricity_consumption_off_peak": 60000.0,
        "electricity_consumption_normal": 50000.0,
        "electricity_consumption_total": 110000.0,
        "electricity_feed_in_off_peak": 6000.0,
        "electricity_feed_in_normal": 5000.0,
        "electricity_feed_in_total": 11000.0,
        "electricity_reading_date": datetime.datetime(2022, 5, 6, 0, 0),
        "electricity_price_single": 0.25,
        "electricity_price_off_peak": 0.2,
        "electricity_price_normal": 0.3,
        "electricity_feed_in_compensation": 0.08,
        "electricity_feed_in_cost": 0.01,
        "gas_consumption": None,
        "gas_reading_date": None,
        "gas_price": None,
    }


def test_with_old_tariffs_api(mock_api):
    mock_api(has_rates=False)

    greenchoice_api = GreenchoiceApi("fake_user", "fake_password")
    result = greenchoice_api.sync_update()

    assert result.model_dump() == {
        "electricity_consumption_off_peak": 60000.0,
        "electricity_consumption_normal": 50000.0,
        "electricity_consumption_total": 110000.0,
        "electricity_feed_in_off_peak": 6000.0,
        "electricity_feed_in_normal": 5000.0,
        "electricity_feed_in_total": 11000.0,
        "electricity_reading_date": datetime.datetime(2022, 5, 6, 0, 0),
        "electricity_price_single": None,
        "electricity_price_off_peak": None,
        "electricity_price_normal": None,
        "electricity_feed_in_compensation": None,
        "electricity_feed_in_cost": None,
        "gas_consumption": 10000.0,
        "gas_reading_date": datetime.datetime(2022, 5, 6, 0, 0),
        "gas_price": None,
    }


def test_update_request_with_agreement_id(
    mock_api,
):
    mock_api()

    greenchoice_api = GreenchoiceApi(
        "fake_user", "fake_password", customer_number=2222, agreement_id=1111
    )
    result = greenchoice_api.sync_update()

    assert result.model_dump() == {
        "electricity_consumption_off_peak": 60000.0,
        "electricity_consumption_normal": 50000.0,
        "electricity_consumption_total": 110000.0,
        "electricity_feed_in_off_peak": 6000.0,
        "electricity_feed_in_normal": 5000.0,
        "electricity_feed_in_total": 11000.0,
        "electricity_reading_date": datetime.datetime(2022, 5, 6, 0, 0),
        "electricity_price_single": 0.25,
        "electricity_price_off_peak": 0.2,
        "electricity_price_normal": 0.3,
        "electricity_feed_in_compensation": 0.08,
        "electricity_feed_in_cost": 0.01,
        "gas_consumption": 10000.0,
        "gas_reading_date": datetime.datetime(2022, 5, 6, 0, 0),
        "gas_price": 0.8,
    }
