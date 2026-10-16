"""Tests for LogShed binary sensor platform."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.logshed.api import LogShedApiClient, LogShedMetrics


async def test_binary_sensors_state_and_attributes(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
    mock_metrics: LogShedMetrics,
) -> None:
    """Test all LogShed binary sensors register with correct states and attributes."""
    mock_config_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.logshed.LogShedApiClient",
            return_value=mock_api_client,
        ),
        patch("custom_components.logshed.PLATFORMS", [Platform.BINARY_SENSOR]),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

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
