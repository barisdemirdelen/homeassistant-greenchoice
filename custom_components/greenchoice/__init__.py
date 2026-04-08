"""The Greenchoice integration."""

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .api import GreenchoiceApi
from .const import CONF_AGREEMENT_ID, CONF_CUSTOMER_NUMBER, DOMAIN
from .sensor import GreenchoiceDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

SERVICE_REIMPORT_HOURLY_STATISTICS = "reimport_hourly_statistics"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""
    try:
        api = GreenchoiceApi(
            entry.data[CONF_EMAIL],
            entry.data[CONF_PASSWORD],
            entry.data.get(CONF_CUSTOMER_NUMBER),
            entry.data.get(CONF_AGREEMENT_ID),
        )
        coordinator = GreenchoiceDataUpdateCoordinator(hass, api, entry)

        # Register shutdown handler
        async def async_close_session(event):
            await coordinator.async_shutdown()

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_close_session)

        await coordinator.async_config_entry_first_refresh()

        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        # Register the reimport action once (shared across all config entries).
        if not hass.services.has_service(DOMAIN, SERVICE_REIMPORT_HOURLY_STATISTICS):
            _register_services(hass)

        return True
    except Exception as e:
        _LOGGER.error("Failed to setup Greenchoice integration: %s", e)
        return False


def _register_services(hass: HomeAssistant) -> None:
    """Register domain-wide actions."""

    async def handle_reimport_hourly_statistics(call: ServiceCall) -> None:
        start_date = call.data["start_date"]
        target_entry_id: str | None = call.data.get("config_entry_id")
        entries = hass.data.get(DOMAIN, {})
        if target_entry_id:
            entries = {target_entry_id: entries[target_entry_id]} if target_entry_id in entries else {}
        for entry_id, coordinator in list(entries.items()):
            try:
                await coordinator.async_force_reimport(start_date)
            except Exception as err:
                config_entry = hass.config_entries.async_get_entry(entry_id)
                title = config_entry.title if config_entry else entry_id
                _LOGGER.error("Reimport failed for %s: %s", title, err)

    hass.services.async_register(
        DOMAIN,
        SERVICE_REIMPORT_HOURLY_STATISTICS,
        handle_reimport_hourly_statistics,
        schema=vol.Schema({
            vol.Required("start_date"): cv.date,
            vol.Optional("config_entry_id"): cv.string,
        }),
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: GreenchoiceDataUpdateCoordinator = hass.data[DOMAIN][
            entry.entry_id
        ]
        await coordinator.async_shutdown()
        hass.data[DOMAIN].pop(entry.entry_id)

        # Remove the shared service when the last entry is unloaded.
        if not hass.data.get(DOMAIN):
            hass.services.async_remove(DOMAIN, SERVICE_REIMPORT_HOURLY_STATISTICS)

    return unload_ok
