"""Tests for LogShed button platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.logshed.api import (
    LogShedApiClient,
    LogShedBadRequest,
    LogShedConflict,
    LogShedRateLimited,
)


async def test_button_press_success(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test pressing prune and vacuum buttons successfully."""
    mock_config_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.logshed.LogShedApiClient",
            return_value=mock_api_client,
        ),
        patch("custom_components.logshed.PLATFORMS", [Platform.BUTTON]),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    # Press prune button
    await hass.services.async_call(
        BUTTON_DOMAIN,
        "press",
        {"entity_id": "button.logshed_prune_database"},
        blocking=True,
    )
    mock_api_client.async_trigger_prune.assert_awaited_once()

    # Press vacuum button
    await hass.services.async_call(
        BUTTON_DOMAIN,
        "press",
        {"entity_id": "button.logshed_vacuum_database"},
        blocking=True,
    )
    mock_api_client.async_trigger_vacuum.assert_awaited_once()


async def test_prune_button_errors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test prune button conflict and cooldown error handling."""
    mock_config_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.logshed.LogShedApiClient",
            return_value=mock_api_client,
        ),
        patch("custom_components.logshed.PLATFORMS", [Platform.BUTTON]),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    # Conflict 409
    mock_api_client.async_trigger_prune = AsyncMock(
        side_effect=LogShedConflict("Operation in progress")
    )
    with pytest.raises(HomeAssistantError, match="already in progress"):
        await hass.services.async_call(
            BUTTON_DOMAIN,
            "press",
            {"entity_id": "button.logshed_prune_database"},
            blocking=True,
        )

    # Cooldown 429
    mock_api_client.async_trigger_prune = AsyncMock(
        side_effect=LogShedRateLimited("Cooldown active", retry_after=120)
    )
    with pytest.raises(HomeAssistantError, match="Prune cooldown active"):
        await hass.services.async_call(
            BUTTON_DOMAIN,
            "press",
            {"entity_id": "button.logshed_prune_database"},
            blocking=True,
        )


async def test_vacuum_button_errors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test vacuum button conflict, disk space, and cooldown error handling."""
    mock_config_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.logshed.LogShedApiClient",
            return_value=mock_api_client,
        ),
        patch("custom_components.logshed.PLATFORMS", [Platform.BUTTON]),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    # Conflict 409
    mock_api_client.async_trigger_vacuum = AsyncMock(
        side_effect=LogShedConflict("Operation in progress")
    )
    with pytest.raises(HomeAssistantError, match="already in progress"):
        await hass.services.async_call(
            BUTTON_DOMAIN,
            "press",
            {"entity_id": "button.logshed_vacuum_database"},
            blocking=True,
        )

    # Insufficient disk space 400
    mock_api_client.async_trigger_vacuum = AsyncMock(
        side_effect=LogShedBadRequest("Insufficient disk space")
    )
    with pytest.raises(HomeAssistantError, match="Insufficient disk space for VACUUM"):
        await hass.services.async_call(
            BUTTON_DOMAIN,
            "press",
            {"entity_id": "button.logshed_vacuum_database"},
            blocking=True,
        )

    # Cooldown 429
    mock_api_client.async_trigger_vacuum = AsyncMock(
        side_effect=LogShedRateLimited("Cooldown active", retry_after=60)
    )
    with pytest.raises(HomeAssistantError, match="Vacuum cooldown active"):
        await hass.services.async_call(
            BUTTON_DOMAIN,
            "press",
            {"entity_id": "button.logshed_vacuum_database"},
            blocking=True,
        )
