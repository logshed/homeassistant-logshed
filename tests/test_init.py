"""Tests for LogShed integration lifecycle setup and unload."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.logshed.api import (
    LogShedApiClient,
    LogShedAuthInfo,
    LogShedCannotConnect,
    LogShedInvalidAuth,
    LogShedMetrics,
)
from custom_components.logshed.const import (
    DOMAIN,
    SERVICE_DISABLE_MAINTENANCE,
    SERVICE_ENABLE_MAINTENANCE,
)

from .conftest import MOCK_INSTANCE_ID, setup_integration


async def test_setup_and_unload_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test full setup and unload of LogShed integration."""
    await setup_integration(hass, mock_config_entry, mock_api_client)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.runtime_data.coordinator.api is mock_api_client
    assert mock_config_entry.runtime_data.scopes == ["*"]

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
    # Services are registered once for the integration and stay after unload
    assert hass.services.has_service(DOMAIN, SERVICE_ENABLE_MAINTENANCE)
    assert hass.services.has_service(DOMAIN, SERVICE_DISABLE_MAINTENANCE)


async def test_setup_invalid_auth_starts_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test a rejected token fails setup and starts a reauth flow."""
    mock_api_client.async_verify_auth = AsyncMock(side_effect=LogShedInvalidAuth("revoked"))
    await setup_integration(hass, mock_config_entry, mock_api_client)

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


async def test_setup_missing_system_read_starts_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test a token without system:read fails setup with an auth error."""
    mock_api_client.async_verify_auth = AsyncMock(
        return_value=LogShedAuthInfo(valid=True, name="Logs", scopes=["logs:read"], expires_at=None)
    )
    await setup_integration(hass, mock_config_entry, mock_api_client)

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    mock_api_client.async_get_system_metrics.assert_not_awaited()


async def test_setup_unreachable_retries(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test an unreachable server puts the entry into setup retry."""
    mock_api_client.async_verify_auth = AsyncMock(side_effect=LogShedCannotConnect("down"))
    await setup_integration(hass, mock_config_entry, mock_api_client)

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_device_named_after_server(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
    mock_metrics: LogShedMetrics,
) -> None:
    """Test the device and default entity IDs follow the LogShed server name."""
    mock_metrics.server_name = "Homelab Logs"
    await setup_integration(hass, mock_config_entry, mock_api_client)

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, MOCK_INSTANCE_ID)})
    assert device is not None
    assert device.name == "Homelab Logs"
    assert hass.states.get("sensor.homelab_logs_ingestion_rate") is not None
