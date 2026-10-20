"""Tests for LogShed update platform."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.logshed.api import (
    LogShedApiClient,
    LogShedCannotConnect,
    LogShedNotFound,
    LogShedVersion,
)

from .conftest import MOCK_INSTANCE_ID, MOCK_VERSION_RESPONSE, setup_integration

ENTITY_ID = "update.logshed_update"


def _version(**changes) -> LogShedVersion:
    return LogShedVersion.from_dict({**MOCK_VERSION_RESPONSE, **changes})


async def test_update_available(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test the update entity shows a newer stable release."""
    await setup_integration(hass, mock_config_entry, mock_api_client, [Platform.UPDATE])

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == "on"
    assert state.attributes["installed_version"] == "1.3.0"
    assert state.attributes["latest_version"] == "1.4.0"
    assert (
        state.attributes["release_url"] == "https://github.com/logshed/logshed/releases/tag/v1.4.0"
    )
    assert state.attributes["supported_features"] == 0

    entry = er.async_get(hass).async_get(ENTITY_ID)
    assert entry is not None
    assert entry.unique_id == f"{MOCK_INSTANCE_ID}_update"
    assert entry.entity_category is EntityCategory.DIAGNOSTIC

    interval = mock_config_entry.runtime_data.version_coordinator.update_interval
    assert interval.total_seconds() == 3600


async def test_update_up_to_date(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test the update entity is off when the installed version is the latest."""
    mock_api_client.async_get_version = AsyncMock(
        return_value=_version(latest_version="1.3.0", update_available=False)
    )
    await setup_integration(hass, mock_config_entry, mock_api_client, [Platform.UPDATE])

    assert hass.states.get(ENTITY_ID).state == "off"


async def test_update_follows_logshed_comparison(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test a pre-release install is compared the way LogShed compares it."""
    mock_api_client.async_get_version = AsyncMock(
        return_value=_version(
            current_version="1.4.0-beta.2", latest_version="1.3.0", update_available=False
        )
    )
    await setup_integration(hass, mock_config_entry, mock_api_client, [Platform.UPDATE])

    assert hass.states.get(ENTITY_ID).state == "off"


async def test_update_unknown_when_check_disabled(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test the state is unknown when LogShed's update check is off or failed."""
    mock_api_client.async_get_version = AsyncMock(
        return_value=_version(latest_version=None, update_available=False, check_enabled=False)
    )
    await setup_integration(hass, mock_config_entry, mock_api_client, [Platform.UPDATE])

    state = hass.states.get(ENTITY_ID)
    assert state.state == "unknown"
    assert state.attributes["installed_version"] == "1.3.0"
    assert state.attributes["release_url"] is None


async def test_update_not_created_without_endpoint(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test a LogShed server without the version endpoint gets no update entity."""
    mock_api_client.async_get_version = AsyncMock(side_effect=LogShedNotFound("Not Found"))
    await setup_integration(hass, mock_config_entry, mock_api_client, [Platform.UPDATE])

    assert hass.states.get(ENTITY_ID) is None
    assert mock_config_entry.runtime_data.version_coordinator is None


async def test_update_unavailable_when_first_check_fails(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test a failed first version check does not block setup."""
    mock_api_client.async_get_version = AsyncMock(side_effect=LogShedCannotConnect("down"))
    await setup_integration(hass, mock_config_entry, mock_api_client, [Platform.UPDATE])

    assert mock_config_entry.runtime_data.version_coordinator is not None
    assert hass.states.get(ENTITY_ID).state == "unavailable"

    mock_api_client.async_get_version = AsyncMock(return_value=_version())
    await mock_config_entry.runtime_data.version_coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == "on"
