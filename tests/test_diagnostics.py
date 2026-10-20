"""Tests for LogShed diagnostics."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.logshed.api import LogShedApiClient
from custom_components.logshed.diagnostics import async_get_config_entry_diagnostics

from .conftest import MOCK_HOST, MOCK_INSTANCE_ID, MOCK_TOKEN, setup_integration


async def test_diagnostics_redact_token(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test diagnostics include entry settings and metrics with the API token redacted."""
    await setup_integration(hass, mock_config_entry, mock_api_client)

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert result["entry"]["data"]["api_token"] == "**REDACTED**"
    assert result["entry"]["data"]["host"] == MOCK_HOST
    assert result["entry"]["options"]["scan_interval"] == 30
    assert result["scopes"] == ["*"]
    assert result["last_update_success"] is True
    assert result["metrics"]["instance_id"] == MOCK_INSTANCE_ID
    assert result["metrics"]["udp_receive_errors"] == 7
    assert result["version"]["latest_version"] == "1.4.0"
    assert MOCK_TOKEN not in str(result)
