import datetime
import inspect
import json
import re
from contextlib import contextmanager
from datetime import UTC, date, time, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import parse_qs, urlparse

import aiohttp
import pytest
from aioresponses import CallbackResult, aioresponses
from homeassistant.const import CONF_NAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.greenchoice.api import BASE_URL
from custom_components.greenchoice.const import DOMAIN
from custom_components.greenchoice.ha_external_statistics import (
    external_statistic as _ext_stat_mod,
)
from custom_components.greenchoice.ha_external_statistics import (
    recorder as _recorder_mod,
)

_PATCH_ADD_STAT = f"{_ext_stat_mod.__name__}.async_add_external_statistics"
_PATCH_GET_INSTANCE = f"{_recorder_mod.__name__}.get_instance"
_PATCH_SDP = f"{_recorder_mod.__name__}.statistics_during_period"

# source https://github.com/pnuckowski/aioresponses/pull/288
# todo Delete when aioresponses updates its compatibility with aiohttp
# aiohttp 3.14 added a required keyword-only ``stream_writer`` argument to
# ``ClientResponse.__init__``. aioresponses (<=0.7.9) builds mocked responses
# without it, so every mocked request raises ``TypeError: ... missing 1
# required keyword-only argument: 'stream_writer'``. aiohttp only reads
# ``stream_writer.output_size``, so a ``Mock(output_size=0)`` suffices.
#
# This mirrors the upstream fix (aioresponses#288, tracking aioresponses#289).
# The signature guard makes it a no-op on aiohttp < 3.14 and once aioresponses
# ships a release that supplies the argument itself; remove this shim then.
_response_init = aiohttp.ClientResponse.__init__
if "stream_writer" in inspect.signature(_response_init).parameters:

    def _patched_response_init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        kwargs.setdefault("stream_writer", Mock(output_size=0))
        _response_init(self, *args, **kwargs)

    aiohttp.ClientResponse.__init__ = _patched_response_init


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
def rate_details_response(data_folder):
    with data_folder.joinpath("test_rate_details.json").open() as f:
        return json.load(f)


@pytest.fixture
def rate_details_response_gas_only(data_folder):
    """A gas-only agreement: the electricity contract has ended."""
    with data_folder.joinpath("test_rate_details.json").open() as f:
        response = json.load(f)
    response["electricityRates"] = None
    return response


@pytest.fixture
def rate_details_response_empty(data_folder):
    """No gas and no electricity — the shape that silently blanked the sensors."""
    with data_folder.joinpath("test_rate_details.json").open() as f:
        response = json.load(f)
    response["electricityRates"] = None
    response["gasRates"] = None
    return response


@pytest.fixture
def rate_details_response_bad_electricity(data_folder):
    """Electricity in a shape the model doesn't expect, gas still valid.

    Guards gas against electricity: the electricity mapping was
    derived from the portal's frontend rather than an observed response, so a
    wrong guess there must not take the gas price down with it.
    """
    with data_folder.joinpath("test_rate_details.json").open() as f:
        response = json.load(f)
    rates = response["electricityRates"]["standardVariableRates"]
    # A scalar where a rate object is expected, and vice versa.
    rates["deliverySingle"] = 0.25
    rates["feedInCompensation"] = {"rateIncludingVat": 0.08}
    return response


@pytest.fixture
def rate_details_response_without_gas(data_folder):
    with data_folder.joinpath("test_rate_details.json").open() as f:
        response = json.load(f)
    response["gasRates"] = None
    return response


@pytest.fixture
def rate_details_response_without_gas_single(data_folder):
    """Electricity-only, single-rate contract: no separate normal/low rates."""
    with data_folder.joinpath("test_rate_details.json").open() as f:
        response = json.load(f)
    response["gasRates"] = None

    rates = response["electricityRates"]["standardVariableRates"]
    rates["deliveryNormal"] = None
    rates["deliveryLow"] = None
    return response


@pytest.fixture
def meters_response(data_folder):
    with data_folder.joinpath("test_meters.json").open() as f:
        return json.load(f)


@pytest.fixture
def meters_response_without_gas(data_folder):
    with data_folder.joinpath("test_meters.json").open() as f:
        response = json.load(f)
    response["hasGas"] = False
    for month in response["months"]:
        month["readings"] = [r for r in month["readings"] if r["gas"] is None]
    return response


@pytest.fixture
def account_response(data_folder):
    with data_folder.joinpath("test_account.json").open() as f:
        return json.load(f)


@pytest.fixture
def account_response_without_profiles(data_folder):
    """An account whose customers have no addresses — nothing to poll."""
    with data_folder.joinpath("test_account.json").open() as f:
        response = json.load(f)
    response["preferences"] = None
    for customer in response["customers"]:
        customer["addresses"] = []
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
    meters_response,
    account_response,
    account_response_without_profiles,
    contract_response_callback,
    rate_details_response,
    rate_details_response_without_gas,
    rate_details_response_without_gas_single,
    rate_details_response_gas_only,
    rate_details_response_empty,
    rate_details_response_bad_electricity,
    meters_response_without_gas,
):
    with aioresponses() as mocked:

        def _mock_api(
            has_gas: bool = True,
            has_rates: bool = True,
            has_profiles: bool = True,
            double_rate: bool = True,
            has_electricity: bool = True,
            empty_rates: bool = False,
            bad_electricity: bool = False,
            consumptions: dict | None = None,
        ):
            mocker.patch(
                "custom_components.greenchoice.auth.Auth.refresh_session",
                return_value=None,
            )

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
                f"{BASE_URL}/api/v2/account",
                payload=account_response
                if has_profiles
                else account_response_without_profiles,
                repeat=True,
            )

            mocked.get(
                (
                    f"{BASE_URL}/api/v2/customers/2222/agreements/1111/meter-readings/"
                    f"{datetime.datetime.now(datetime.UTC).year}/"
                ),
                payload=meters_response if has_gas else meters_response_without_gas,
            )

            rate_details_url = re.compile(
                re.escape(BASE_URL)
                + r"/api/v3/customers/2222/agreements/1111/rate-details\?.*"
            )
            if has_rates:
                payload = rate_details_response
                if not has_gas:
                    payload = rate_details_response_without_gas
                if not has_gas and not double_rate:
                    payload = rate_details_response_without_gas_single
                if not has_electricity:
                    payload = rate_details_response_gas_only
                if empty_rates:
                    payload = rate_details_response_empty
                if bad_electricity:
                    payload = rate_details_response_bad_electricity
                mocked.get(rate_details_url, payload=payload)
            else:
                mocked.get(rate_details_url, payload={"status": 404}, status=404)

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
    """Patch async_add_external_statistics in external_statistic for the duration of the test."""
    with patch(_PATCH_ADD_STAT, new=Mock()) as m:
        yield m


@pytest.fixture
def patch_today():
    """Factory: patches _today() on the coordinator to fix 'today' for tests.

    Usage: ``with patch_today(date(2026, 3, 28)):``
    """
    from custom_components.greenchoice.sensor import GreenchoiceDataUpdateCoordinator

    def _patch(return_value):
        if isinstance(return_value, datetime.datetime):
            return_value = return_value.date()
        return patch.object(
            GreenchoiceDataUpdateCoordinator,
            "_today",
            return_value=return_value,
        )

    return _patch


@pytest.fixture
def patch_recorder_days():
    """Factory: returns a context manager that stubs the HA recorder statistics API.

    Patches ``get_instance`` and ``statistics_during_period`` in recorder.py —
    the recorder boundary our code crosses — so tests remain independent of
    internal HA implementation.

    Pass a ``{date: sum}`` dict to represent end-of-day cumulative sums already
    present in the recorder.  When ``async_get_last_sum`` queries a 25-hour window
    the fixture returns the latest entry whose 23:00 UTC timestamp falls inside
    the queried range.
    """

    def _patch(day_sums: dict[date, float] | None = None):
        if not day_sums:
            day_sums = {}

        def _fake_statistics_during_period(
            _hass, _start, _end, statistic_ids, _period, _units, _types
        ):
            if not statistic_ids:
                return {}
            sid = next(iter(statistic_ids))
            rows = [
                {
                    "start": datetime.datetime.combine(d, time(23, 0), tzinfo=UTC),
                    "sum": s,
                }
                for d, s in sorted(day_sums.items())
                if _start
                <= datetime.datetime.combine(d, time(23, 0), tzinfo=UTC)
                < _end
            ]
            return {sid: rows} if rows else {}

        mock_recorder_instance = Mock()
        mock_recorder_instance.async_add_executor_job = AsyncMock(
            side_effect=lambda func, *args, **kwargs: func(*args, **kwargs)
        )

        @contextmanager
        def _ctx():
            with (
                patch(_PATCH_GET_INSTANCE, return_value=mock_recorder_instance),
                patch(_PATCH_SDP, side_effect=_fake_statistics_during_period),
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
