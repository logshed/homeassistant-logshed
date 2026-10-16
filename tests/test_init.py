"""Tests for LogShed integration lifecycle setup and unload."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.logshed.api import LogShedApiClient
from custom_components.logshed.const import DOMAIN


async def test_setup_and_unload_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test full setup and unload of LogShed integration."""
    mock_config_entry.add_to_hass(hass)

    with patch(
        "custom_components.logshed.LogShedApiClient",
        return_value=mock_api_client,
    ):
        # Setup
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        assert mock_config_entry.state is ConfigEntryState.LOADED
        assert mock_config_entry.entry_id in hass.data[DOMAIN]

        # Unload
        assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
        assert mock_config_entry.entry_id not in hass.data.get(DOMAIN, {})
