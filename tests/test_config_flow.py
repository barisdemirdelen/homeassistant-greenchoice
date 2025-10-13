"""Test config flow for Greenchoice integration."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResultType

from custom_components.greenchoice import GreenchoiceApi
from custom_components.greenchoice.api import ApiError
from custom_components.greenchoice.config_flow import GreenchoiceConfigFlow
from custom_components.greenchoice.const import (
    CONF_AGREEMENT_ID,
    CONF_CUSTOMER_NUMBER,
    CONF_PROFILE,
)
from custom_components.greenchoice.model import Profile


@pytest.fixture
def mock_profiles(profiles_response):
    return GreenchoiceApi.validate_list(Profile, profiles_response, ignore_invalid=True)


@pytest.fixture
def flow(hass):
    flow = GreenchoiceConfigFlow()
    flow.hass = hass
    return flow


@pytest.mark.asyncio
async def test_form_user_step(flow, mock_api):
    """Test the initial user step shows the form."""
    mock_api(has_gas=True, has_rates=True)

    result = await flow.async_step_user()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


@pytest.mark.asyncio
async def test_form_user_step_success(flow, mock_api):
    """Test successful authentication moves to profile step."""
    mock_api(has_gas=True, has_rates=True)

    result = await flow.async_step_user(
        {CONF_EMAIL: "test@example.com", CONF_PASSWORD: "password123"}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "profile"
    assert flow.email == "test@example.com"
    assert flow.password == "password123"
    assert len(flow.profiles) == 2


@pytest.mark.asyncio
async def test_form_user_step_no_profiles(flow, mock_api):
    """Test error when no profiles are found."""
    mock_api(has_profiles=False)

    result = await flow.async_step_user(
        {CONF_EMAIL: "test@example.com", CONF_PASSWORD: "password123"}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "no_profiles"}


@pytest.mark.asyncio
async def test_form_user_step_cannot_connect(flow):
    """Test error when connection fails."""

    with patch("custom_components.greenchoice.config_flow.GreenchoiceApi") as mock_api:
        mock_instance = AsyncMock()
        mock_instance.get_profiles.side_effect = ApiError("(TEST) Connection error")
        mock_api.return_value = mock_instance

        result = await flow.async_step_user(
            {CONF_EMAIL: "test@example.com", CONF_PASSWORD: "password123"}
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.asyncio
async def test_profile_step_shows_form(flow, mock_profiles):
    """Test profile selection step shows the form."""
    flow.email = "test@example.com"
    flow.password = "password123"
    flow.profiles = mock_profiles

    result = await flow.async_step_profile()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "profile"
    assert result["errors"] == {}


@pytest.mark.asyncio
async def test_profile_step_creates_entry(flow, mock_profiles):
    """Test successful profile selection creates entry."""
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
async def test_profile_step_creates_entry_without_custom_name(flow, mock_profiles):
    """Test profile selection uses address when no custom name provided."""
    flow.email = "test@example.com"
    flow.password = "password123"
    flow.profiles = mock_profiles

    result = await flow.async_step_profile({CONF_PROFILE: "2222_1111"})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Greenchoice (Address Street 1 1234AB City)"


@pytest.mark.asyncio
async def test_profile_step_invalid_profile(flow, mock_profiles):
    """Test error when invalid profile is selected."""
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
