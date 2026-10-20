"""Tests for LogShedDataUpdateCoordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.logshed.api import (
    LogShedApiClient,
    LogShedCannotConnect,
    LogShedInvalidAuth,
    LogShedMetrics,
)
from custom_components.logshed.const import (
    CONF_API_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_VERIFY_SSL,
    DOMAIN,
)
from custom_components.logshed.coordinator import LogShedDataUpdateCoordinator

from .conftest import MOCK_HOST, MOCK_INSTANCE_ID, MOCK_TOKEN


async def test_coordinator_update_success(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
    mock_metrics: LogShedMetrics,
) -> None:
    """Test successful coordinator update."""
    coordinator = LogShedDataUpdateCoordinator(hass, mock_api_client, mock_config_entry)
    await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    assert coordinator.data == mock_metrics
    assert coordinator.data.server_name == "LogShed"
    assert coordinator.data.ingest_rate == 42.5


async def test_coordinator_update_auth_failure(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test coordinator raises ConfigEntryAuthFailed on LogShedInvalidAuth."""
    mock_api_client.async_get_system_metrics = AsyncMock(
        side_effect=LogShedInvalidAuth("Token expired")
    )
    coordinator = LogShedDataUpdateCoordinator(hass, mock_api_client, mock_config_entry)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_coordinator_update_network_failure(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test coordinator raises UpdateFailed on LogShedCannotConnect."""
    mock_api_client.async_get_system_metrics = AsyncMock(
        side_effect=LogShedCannotConnect("Connection timed out")
    )
    coordinator = LogShedDataUpdateCoordinator(hass, mock_api_client, mock_config_entry)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_coordinator_custom_scan_interval(
    hass: HomeAssistant,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test coordinator sets update_interval from entry options."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MOCK_INSTANCE_ID,
        title="LogShed (LogShed)",
        data={
            CONF_HOST: MOCK_HOST,
            CONF_API_TOKEN: MOCK_TOKEN,
            CONF_VERIFY_SSL: True,
        },
        options={
            CONF_SCAN_INTERVAL: 15,
        },
    )
    coordinator = LogShedDataUpdateCoordinator(hass, mock_api_client, entry)
    assert coordinator.update_interval is not None
    assert coordinator.update_interval.total_seconds() == 15
