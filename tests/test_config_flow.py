"""Test config flow for Greenchoice integration."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResultType

from custom_components.greenchoice import GreenchoiceApi
from custom_components.greenchoice.config_flow import GreenchoiceConfigFlow
from custom_components.greenchoice.const import (
    CONF_AGREEMENT_ID,
    CONF_CUSTOMER_NUMBER,
    CONF_PROFILE,
)
from custom_components.greenchoice.model import Profile


@pytest.fixture
def mock_profiles(profiles_response):
    return GreenchoiceApi.validate_list(Profile, profiles_response)


@pytest.mark.asyncio
async def test_form_user_step(hass, mock_api):
    """Test the initial user step shows the form."""
    mock_api(has_gas=True, has_rates=True)

    flow = GreenchoiceConfigFlow()
    flow.hass = hass

    result = await flow.async_step_user()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


@pytest.mark.asyncio
async def test_form_user_step_success(hass, mock_api):
    """Test successful authentication moves to profile step."""
    mock_api(has_gas=True, has_rates=True)

    flow = GreenchoiceConfigFlow()
    flow.hass = hass

    result = await flow.async_step_user(
        {CONF_EMAIL: "test@example.com", CONF_PASSWORD: "password123"}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "profile"
    assert flow.email == "test@example.com"
    assert flow.password == "password123"
    assert len(flow.profiles) == 2


@pytest.mark.asyncio
async def test_form_user_step_no_profiles(hass):
    """Test error when no profiles are found."""
    flow = GreenchoiceConfigFlow()
    flow.hass = hass

    with patch("custom_components.greenchoice.config_flow.GreenchoiceApi") as mock_api:
        mock_instance = AsyncMock()
        mock_instance.get_profiles.return_value = []
        mock_api.return_value = mock_instance

        result = await flow.async_step_user(
            {CONF_EMAIL: "test@example.com", CONF_PASSWORD: "password123"}
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "no_profiles"}


@pytest.mark.asyncio
async def test_form_user_step_cannot_connect(hass):
    """Test error when connection fails."""
    flow = GreenchoiceConfigFlow()
    flow.hass = hass

    with patch("custom_components.greenchoice.config_flow.GreenchoiceApi") as mock_api:
        mock_instance = AsyncMock()
        mock_instance.get_profiles.side_effect = Exception("Connection error")
        mock_api.return_value = mock_instance

        result = await flow.async_step_user(
            {CONF_EMAIL: "test@example.com", CONF_PASSWORD: "password123"}
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.asyncio
async def test_profile_step_shows_form(hass, mock_profiles):
    """Test profile selection step shows the form."""
    flow = GreenchoiceConfigFlow()
    flow.hass = hass
    flow.email = "test@example.com"
    flow.password = "password123"
    flow.profiles = mock_profiles

    result = await flow.async_step_profile()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "profile"
    assert result["errors"] == {}


@pytest.mark.asyncio
async def test_profile_step_creates_entry(hass, mock_profiles):
    """Test successful profile selection creates entry."""
    flow = GreenchoiceConfigFlow()
    flow.hass = hass
    flow.email = "test@example.com"
    flow.password = "password123"
    flow.profiles = mock_profiles

    result = await flow.async_step_profile(
        {CONF_PROFILE: "2222_1111", "name": "My Home"}
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Greenchoice (My Home)"
    assert result["data"] == {
        "name": "My Home",
        CONF_EMAIL: "test@example.com",
        CONF_PASSWORD: "password123",
        CONF_CUSTOMER_NUMBER: 2222,
        CONF_AGREEMENT_ID: 1111,
    }


@pytest.mark.asyncio
async def test_profile_step_creates_entry_without_custom_name(hass, mock_profiles):
    """Test profile selection uses address when no custom name provided."""
    flow = GreenchoiceConfigFlow()
    flow.hass = hass
    flow.email = "test@example.com"
    flow.password = "password123"
    flow.profiles = mock_profiles

    result = await flow.async_step_profile({CONF_PROFILE: "2222_1111"})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Greenchoice (Address Street 1 1234AB City)"


@pytest.mark.asyncio
async def test_profile_step_invalid_profile(hass, mock_profiles):
    """Test error when invalid profile is selected."""
    flow = GreenchoiceConfigFlow()
    flow.hass = hass
    flow.email = "test@example.com"
    flow.password = "password123"
    flow.profiles = mock_profiles

    result = await flow.async_step_profile({CONF_PROFILE: "invalid_key"})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "profile"
    assert result["errors"] == {"base": "invalid_profile"}


def test_get_profile_key(mock_profiles):
    """Test profile key generation."""
    flow = GreenchoiceConfigFlow()

    key = flow._get_profile_key(mock_profiles[0])

    assert key == "2222_1111"


def test_format_profile_display_full_address(mock_profiles):
    """Test profile display formatting with full address."""
    flow = GreenchoiceConfigFlow()

    display = flow._format_profile_display(mock_profiles[0])

    assert display == "Address Street 1 1234AB City"


def test_format_profile_display_without_addition(mock_profiles):
    """Test profile display formatting without house number addition."""
    flow = GreenchoiceConfigFlow()

    display = flow._format_profile_display(mock_profiles[1])

    assert display == "Address Street 2 2 1234BC City 2"


def test_format_profile_display_fallback():
    """Test profile display formatting fallback when address is missing."""
    flow = GreenchoiceConfigFlow()
    profile = Profile.model_validate(
        {
            "customerNumber": 99999,
            "agreementId": 11111,
        }
    )

    display = flow._format_profile_display(profile)

    assert display == "Profile 99999/11111"
