"""Tests for LogShed switch platform."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.logshed.api import LogShedApiClient


async def test_maintenance_switch_control(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test maintenance switch turning on and off."""
    mock_config_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.logshed.LogShedApiClient",
            return_value=mock_api_client,
        ),
        patch("custom_components.logshed.PLATFORMS", [Platform.SWITCH]),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = "switch.logshed_maintenance_mode"
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "on"

    # Turn off switch
    await hass.services.async_call(
        SWITCH_DOMAIN,
        "turn_off",
        {"entity_id": entity_id},
        blocking=True,
    )
    mock_api_client.async_disable_maintenance.assert_awaited_once()

    # Turn on switch
    await hass.services.async_call(
        SWITCH_DOMAIN,
        "turn_on",
        {"entity_id": entity_id},
        blocking=True,
    )
    mock_api_client.async_enable_maintenance.assert_awaited_once_with(
        duration_minutes=60,
        reason="Home Assistant maintenance switch",
        log_handling="silence_alerts",
    )
