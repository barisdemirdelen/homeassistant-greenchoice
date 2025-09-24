"""Config flow for Greenchoice integration."""

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_NAME, CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResult

from .api import GreenchoiceApi
from .const import (
    CONF_AGREEMENT_ID,
    CONF_CUSTOMER_NUMBER,
    CONF_PROFILE,
    DEFAULT_NAME,
    DOMAIN,
)
from .model import Profile

_LOGGER = logging.getLogger(__name__)


class GreenchoiceConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Greenchoice."""

    VERSION = 1

    def __init__(self):
        """Initialize config flow."""
        self.email: str | None = None
        self.password: str | None = None
        self.profiles: list[Profile] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - email and password."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self.email = user_input[CONF_EMAIL]
            self.password = user_input[CONF_PASSWORD]

            try:
                # Test the connection and get profiles
                api = GreenchoiceApi(self.email, self.password)

                async with api:
                    self.profiles = await api.get_profiles()

                if not self.profiles:
                    errors["base"] = "no_profiles"
                else:
                    # Move to profile selection step
                    return await self.async_step_profile()

            except Exception as e:
                _LOGGER.exception("Authentication failed: %s", e)
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_profile(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle profile selection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # Find selected profile
                selected_profile_key = user_input[CONF_PROFILE]
                selected_profile = None

                for profile in self.profiles:
                    if self._get_profile_key(profile) == selected_profile_key:
                        selected_profile = profile
                        break

                if selected_profile is None:
                    errors["base"] = "invalid_profile"
                else:
                    # Create entry with selected profile data
                    entry_data: dict[str, Any] = {
                        CONF_NAME: user_input.get("name", DEFAULT_NAME),
                        CONF_EMAIL: self.email,
                        CONF_PASSWORD: self.password,
                        CONF_CUSTOMER_NUMBER: selected_profile.customer_number,
                        CONF_AGREEMENT_ID: selected_profile.agreement_id,
                    }

                    # Use custom name if provided, otherwise use address
                    title = user_input.get("name") or self._format_profile_display(
                        selected_profile
                    )

                    return self.async_create_entry(
                        title=f"Greenchoice ({title})",
                        data=entry_data,
                    )

            except Exception as e:
                _LOGGER.exception("Profile selection failed: %s", e)
                errors["base"] = "unknown"

        # Create profile options for dropdown
        profile_options = {}
        for profile in self.profiles:
            key = self._get_profile_key(profile)
            display = self._format_profile_display(profile)
            profile_options[key] = display

        return self.async_show_form(
            step_id="profile",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PROFILE): vol.In(profile_options),
                    vol.Optional(
                        "name", description="Custom name for this integration"
                    ): str,
                }
            ),
            errors=errors,
        )

    def _get_profile_key(self, profile: Profile) -> str:
        """Generate unique key for profile."""
        return f"{profile.customer_number}_{profile.agreement_id}"

    def _format_profile_display(self, profile: Profile) -> str:
        """Format profile for display in dropdown."""
        # Build address string
        address_parts = []

        if profile.street:
            address_parts.append(profile.street)

        if profile.house_number:
            house_part = str(profile.house_number)
            if profile.house_number_addition:
                house_part += str(profile.house_number_addition)
            address_parts.append(house_part)

        if profile.postal_code:
            address_parts.append(profile.postal_code)

        if profile.city:
            address_parts.append(profile.city)

        if address_parts:
            return " ".join(address_parts)
        else:
            # Fallback if address info is missing
            return f"Profile {profile.customer_number}/{profile.agreement_id}"
