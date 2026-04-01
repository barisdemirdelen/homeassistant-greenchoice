import datetime
import json
import re
from contextlib import contextmanager
from datetime import UTC, date, time, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from aioresponses import CallbackResult, aioresponses
from homeassistant.const import CONF_NAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.greenchoice.api import BASE_URL
from custom_components.greenchoice.const import DOMAIN


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
def consumptions_hour_with_gas_response(data_folder):
    with data_folder.joinpath("test_consumptions_hour_with_gas.json").open() as f:
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
    """Factory: returns a context manager that stubs the HA recorder statistics API.

    Patches ``get_instance`` and ``statistics_during_period`` — the actual recorder
    boundary our code crosses — rather than the internal ``_get_days_with_data``
    helper, so tests survive internal refactoring.

    Pass one dict  → {date: sum} returned for every statistics query.
    Pass two dicts → returned in order (consumption query first, feed-in second).
    """

    def _patch(*day_sums_per_call):
        results = list(day_sums_per_call) if day_sums_per_call else [{}]
        state = {"calls": 0}

        def _fake_statistics_during_period(
            _hass, _start, _end, statistic_ids, _period, _units, _types
        ):
            day_sums = results[min(state["calls"], len(results) - 1)]
            state["calls"] += 1
            if not statistic_ids:
                return {}
            sid = next(iter(statistic_ids))
            # One row per day at 23:00 UTC — the highest sum of the day — so
            # dt_util.as_local gives back the same calendar date in UTC-based tests.
            rows = [
                {"start": datetime.datetime.combine(d, time(23, 0), tzinfo=UTC), "sum": s}
                for d, s in sorted(day_sums.items())
            ]
            return {sid: rows} if rows else {}

        mock_recorder_instance = Mock()
        mock_recorder_instance.async_add_executor_job = AsyncMock(
            side_effect=lambda func, *args, **kwargs: func(*args, **kwargs)
        )

        @contextmanager
        def _ctx():
            with (
                patch(
                    "custom_components.greenchoice.hourly_statistics.get_instance",
                    return_value=mock_recorder_instance,
                ),
                patch(
                    "custom_components.greenchoice.hourly_statistics.statistics_during_period",
                    side_effect=_fake_statistics_during_period,
                ),
            ):
                yield

        return _ctx()

    return _patch


@pytest.fixture
def entry_factory(hass):
    """Factory: create and register a MockConfigEntry with standard test values.

    Usage: ``entry = entry_factory("my_entry_id")``
    """

    def _make(entry_id: str, name: str = "My Home", title: str = "Greenchoice (Test)"):
        e = MockConfigEntry(
            domain=DOMAIN,
            entry_id=entry_id,
            title=title,
            data={CONF_NAME: name},
        )
        e.add_to_hass(hass)
        return e

    return _make


def make_consumptions_payload(
    date_str: str,
    total_delivery: float,
    total_feed_in: float = 0.0,
    gas_delivery: float | None = None,
) -> dict:
    """Build a single-point hourly consumptions API response for the given date."""
    end_str = (date.fromisoformat(date_str) + timedelta(days=1)).isoformat()
    item: dict = {
        "consumedOn": f"{date_str}T00:00:00",
        "electricity": {
            "totalDeliveryConsumption": total_delivery,
            "totalFeedInConsumption": total_feed_in,
            "hasConsumption": True,
        },
        "hasConsumption": True,
    }
    if gas_delivery is not None:
        item["gas"] = {
            "totalDeliveryConsumption": gas_delivery,
            "hasConsumption": True,
        }
    return {
        "interval": "Hour",
        "start": f"{date_str}T00:00:00",
        "end": f"{end_str}T00:00:00",
        "consumptionCosts": [item],
    }


def stat_sum(s) -> float:
    """Extract the sum value from a StatisticData object or dict."""
    return float(s["sum"] if isinstance(s, dict) else s.sum)


@pytest.fixture
def patch_store_save():
    """Patch homeassistant.helpers.storage.Store.async_save for the duration of the test."""
    with patch("homeassistant.helpers.storage.Store.async_save") as mock_save:
        yield mock_save

