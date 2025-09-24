"""The Greenchoice integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import HomeAssistant

from .api import GreenchoiceApi
from .const import CONF_AGREEMENT_ID, CONF_CUSTOMER_NUMBER, DOMAIN
from .sensor import GreenchoiceDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


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

        # This is where failures likely happen - add error handling
        await coordinator.async_config_entry_first_refresh()

        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        return True
    except Exception as e:
        _LOGGER.error("Failed to setup Greenchoice integration: %s", e)
        return False


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: GreenchoiceDataUpdateCoordinator = hass.data[DOMAIN][
            entry.entry_id
        ]
        await coordinator.async_shutdown()
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
