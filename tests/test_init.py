"""Config entry setup behaviour."""

import logging
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_EMAIL, CONF_NAME, CONF_PASSWORD
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.greenchoice.api import ApiError
from custom_components.greenchoice.const import DOMAIN
from custom_components.greenchoice.model import SensorUpdate


@pytest.fixture
def entry(hass):
    e = MockConfigEntry(
        domain=DOMAIN,
        entry_id="setup_entry",
        title="Greenchoice (Test)",
        data={
            CONF_NAME: "My Home",
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "hunter2",
        },
    )
    e.add_to_hass(hass)
    return e


@pytest.fixture(autouse=True)
def _quiet_sqlalchemy():
    """recorder_mock runs SQLAlchemy with echo on; keep test output readable."""
    logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.WARNING)


async def _setup(hass, entry, **update_mock_kwargs):
    """Run entry setup with the network layer stubbed out."""
    with (
        patch(
            "custom_components.greenchoice.auth.Auth.refresh_session",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "custom_components.greenchoice.api.GreenchoiceApi.update",
            new=AsyncMock(**update_mock_kwargs),
        ),
        patch(
            "custom_components.greenchoice.sensor."
            "GreenchoiceDataUpdateCoordinator.async_run_statistics_update",
            new=AsyncMock(return_value=None),
        ),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


async def test_setup_succeeds(recorder_mock, hass, enable_custom_integrations, entry):
    await _setup(hass, entry, return_value=SensorUpdate())

    assert entry.state is ConfigEntryState.LOADED


async def test_api_error_schedules_retry(
    recorder_mock, hass, enable_custom_integrations, entry
):
    """A failing first fetch must leave the entry retryable, not dead."""
    await _setup(hass, entry, side_effect=ApiError("HTTP Error: boom"))

    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert "boom" in str(entry.reason)


async def test_unexpected_error_schedules_retry(
    recorder_mock, hass, enable_custom_integrations, entry, caplog
):
    """Unexpected exceptions retry too, and keep their traceback in the log."""
    await _setup(
        hass, entry, side_effect=TypeError("'ClientSession' object is not callable")
    )

    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert "'ClientSession' object is not callable" in caplog.text
    assert "Traceback" in caplog.text
