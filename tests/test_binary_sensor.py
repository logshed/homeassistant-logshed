"""Tests for LogShed binary sensor platform."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.logshed.api import LogShedApiClient, LogShedCannotConnect

from .conftest import setup_integration


async def test_binary_sensors_state_and_attributes(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test all LogShed binary sensors register with correct states and attributes."""
    await setup_integration(hass, mock_config_entry, mock_api_client, [Platform.BINARY_SENSOR])

    # 1. Alert State (problem)
    state = hass.states.get("binary_sensor.logshed_alert_state")
    assert state is not None
    assert state.state == "on"
    assert state.attributes.get("device_class") == "problem"
    assert state.attributes.get("recent_firing_count") == 2
    assert state.attributes.get("last_rule_name") == "Critical Error Spike"
    assert state.attributes.get("last_triggered_at") == "2026-10-15T14:30:00Z"

    # 2. Maintenance Active
    state = hass.states.get("binary_sensor.logshed_maintenance_active")
    assert state is not None
    assert state.state == "on"
    assert state.attributes.get("active_sessions_count") == 1
    assert state.attributes.get("log_handling") == "silence_alerts"
    assert state.attributes.get("until") == "2026-10-15T16:00:00Z"

    # 3. Connectivity
    state = hass.states.get("binary_sensor.logshed_connectivity")
    assert state is not None
    assert state.state == "on"
    assert state.attributes.get("device_class") == "connectivity"
    entry = er.async_get(hass).async_get("binary_sensor.logshed_connectivity")
    assert entry is not None
    assert entry.entity_category is EntityCategory.DIAGNOSTIC


async def test_connectivity_turns_off_when_polling_fails(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test the connectivity sensor reports off, not unavailable, when LogShed is down."""
    await setup_integration(hass, mock_config_entry, mock_api_client, [Platform.BINARY_SENSOR])

    mock_api_client.async_get_system_metrics = AsyncMock(side_effect=LogShedCannotConnect("down"))
    await mock_config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get("binary_sensor.logshed_connectivity").state == "off"
    assert hass.states.get("binary_sensor.logshed_alert_state").state == "unavailable"
