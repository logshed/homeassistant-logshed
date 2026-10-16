"""Tests for LogShed services."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.logshed.api import LogShedApiClient, LogShedConflict
from custom_components.logshed.const import (
    DOMAIN,
    SERVICE_DISABLE_MAINTENANCE,
    SERVICE_ENABLE_MAINTENANCE,
)


async def test_enable_maintenance_service_default_params(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test enable_maintenance service call with default parameters."""
    mock_config_entry.add_to_hass(hass)

    with patch(
        "custom_components.logshed.LogShedApiClient",
        return_value=mock_api_client,
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_ENABLE_MAINTENANCE,
        {},
        blocking=True,
    )
    mock_api_client.async_enable_maintenance.assert_awaited_once_with(
        duration_minutes=30,
        reason="Home Assistant automation",
        log_handling="silence_alerts",
        target_app=None,
        target_host=None,
    )


async def test_enable_maintenance_service_custom_params(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test enable_maintenance service call with customized parameters and targeting."""
    mock_config_entry.add_to_hass(hass)

    with patch(
        "custom_components.logshed.LogShedApiClient",
        return_value=mock_api_client,
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_ENABLE_MAINTENANCE,
        {
            "config_entry_id": mock_config_entry.entry_id,
            "duration_minutes": 90,
            "reason": "Upgrading cluster",
            "log_handling": "drop_errors",
            "target_app": "redis",
            "target_host": "db-node-01",
        },
        blocking=True,
    )
    mock_api_client.async_enable_maintenance.assert_awaited_once_with(
        duration_minutes=90,
        reason="Upgrading cluster",
        log_handling="drop_errors",
        target_app="redis",
        target_host="db-node-01",
    )


async def test_enable_maintenance_session_limit_exceeded(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test enable_maintenance raises error when active session limit (20) reached."""
    mock_config_entry.add_to_hass(hass)

    with patch(
        "custom_components.logshed.LogShedApiClient",
        return_value=mock_api_client,
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    mock_api_client.async_enable_maintenance = AsyncMock(
        side_effect=LogShedConflict("Maximum active sessions reached (20)")
    )
    with pytest.raises(HomeAssistantError, match="Maximum active maintenance sessions limit"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_ENABLE_MAINTENANCE,
            {"duration_minutes": 60},
            blocking=True,
        )


async def test_disable_maintenance_service(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test disable_maintenance service call with and without session_id."""
    mock_config_entry.add_to_hass(hass)

    with patch(
        "custom_components.logshed.LogShedApiClient",
        return_value=mock_api_client,
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    # Disable all sessions
    await hass.services.async_call(
        DOMAIN,
        SERVICE_DISABLE_MAINTENANCE,
        {},
        blocking=True,
    )
    mock_api_client.async_disable_maintenance.assert_awaited_once_with(session_id=None)

    # Disable specific session
    mock_api_client.async_disable_maintenance.reset_mock()
    await hass.services.async_call(
        DOMAIN,
        SERVICE_DISABLE_MAINTENANCE,
        {"session_id": "sess-abc-123"},
        blocking=True,
    )
    mock_api_client.async_disable_maintenance.assert_awaited_once_with(session_id="sess-abc-123")
