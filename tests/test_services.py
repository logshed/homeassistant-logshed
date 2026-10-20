"""Tests for LogShed services."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.logshed.api import (
    LogShedApiClient,
    LogShedAuthInfo,
    LogShedConflict,
    LogShedMetrics,
    LogShedNotFound,
)
from custom_components.logshed.const import (
    CONF_API_TOKEN,
    DOMAIN,
    SERVICE_DISABLE_MAINTENANCE,
    SERVICE_ENABLE_MAINTENANCE,
)

from .conftest import (
    MOCK_SESSION_UNTIL,
    MOCK_SYSTEM_METRICS_RESPONSE,
    MOCK_TOKEN,
    setup_integration,
)

SECOND_INSTANCE_ID = "87654321-4321-8765-4321-876543218765"


def _second_instance(
    mock_api_client: LogShedApiClient, mock_auth_info: LogShedAuthInfo
) -> tuple[MockConfigEntry, LogShedApiClient]:
    """Return a config entry and API client for a second LogShed instance."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=SECOND_INSTANCE_ID,
        title="LogShed (Second)",
        data={CONF_HOST: "http://192.168.1.200:8000", CONF_API_TOKEN: MOCK_TOKEN},
    )
    metrics = LogShedMetrics.from_dict(
        {
            **MOCK_SYSTEM_METRICS_RESPONSE,
            "instance_id": SECOND_INSTANCE_ID,
            "server_name": "Second",
        }
    )
    client = LogShedApiClient("http://192.168.1.200:8000", MOCK_TOKEN, AsyncMock())
    client.async_verify_auth = AsyncMock(return_value=mock_auth_info)
    client.async_get_system_metrics = AsyncMock(return_value=metrics)
    client.async_enable_maintenance = AsyncMock(
        return_value={"session_id": "sess-456", "active": True, "until": MOCK_SESSION_UNTIL}
    )
    client.async_disable_maintenance = AsyncMock(
        return_value={"active": False, "terminated_sessions": 1}
    )
    return entry, client


async def test_enable_maintenance_service_default_params(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test enable_maintenance service call with default parameters."""
    await setup_integration(hass, mock_config_entry, mock_api_client)

    await hass.services.async_call(DOMAIN, SERVICE_ENABLE_MAINTENANCE, {}, blocking=True)
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
    await setup_integration(hass, mock_config_entry, mock_api_client)

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


async def test_enable_maintenance_returns_sessions(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
    mock_auth_info: LogShedAuthInfo,
) -> None:
    """Test enable_maintenance returns the session started on each instance."""
    await setup_integration(hass, mock_config_entry, mock_api_client)
    second_entry, second_client = _second_instance(mock_api_client, mock_auth_info)
    await setup_integration(hass, second_entry, second_client)

    response = await hass.services.async_call(
        DOMAIN, SERVICE_ENABLE_MAINTENANCE, {}, blocking=True, return_response=True
    )
    assert response == {
        "sessions": [
            {
                "config_entry_id": mock_config_entry.entry_id,
                "session_id": "sess-123",
                "until": MOCK_SESSION_UNTIL,
            },
            {
                "config_entry_id": second_entry.entry_id,
                "session_id": "sess-456",
                "until": MOCK_SESSION_UNTIL,
            },
        ]
    }

    # Targeting one instance starts one session
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_ENABLE_MAINTENANCE,
        {"config_entry_id": second_entry.entry_id},
        blocking=True,
        return_response=True,
    )
    assert [s["session_id"] for s in response["sessions"]] == ["sess-456"]
    assert mock_api_client.async_enable_maintenance.await_count == 1


async def test_enable_maintenance_session_limit_exceeded(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test enable_maintenance raises error when active session limit (20) reached."""
    await setup_integration(hass, mock_config_entry, mock_api_client)

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


async def test_service_unknown_config_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test targeting an unknown config entry raises a validation error."""
    await setup_integration(hass, mock_config_entry, mock_api_client)

    with pytest.raises(ServiceValidationError, match="not found"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_ENABLE_MAINTENANCE,
            {"config_entry_id": "does-not-exist"},
            blocking=True,
        )


async def test_service_without_loaded_instances(hass: HomeAssistant) -> None:
    """Test the services exist before any entry loads and fail clearly."""

    assert await async_setup_component(hass, DOMAIN, {})
    with pytest.raises(ServiceValidationError, match="No LogShed instances are loaded"):
        await hass.services.async_call(DOMAIN, SERVICE_DISABLE_MAINTENANCE, {}, blocking=True)


async def test_service_requires_maintenance_write(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test the services refuse an instance whose token lacks maintenance:write."""
    mock_api_client.async_verify_auth = AsyncMock(
        return_value=LogShedAuthInfo(
            valid=True, name="Read only", scopes=["system:read"], expires_at=None
        )
    )
    await setup_integration(hass, mock_config_entry, mock_api_client)

    for service in (SERVICE_ENABLE_MAINTENANCE, SERVICE_DISABLE_MAINTENANCE):
        with pytest.raises(ServiceValidationError, match="lacks the 'maintenance:write' scope"):
            await hass.services.async_call(DOMAIN, service, {}, blocking=True)
    mock_api_client.async_enable_maintenance.assert_not_awaited()
    mock_api_client.async_disable_maintenance.assert_not_awaited()


async def test_disable_maintenance_service(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test disable_maintenance service call with and without session_id."""
    await setup_integration(hass, mock_config_entry, mock_api_client)

    # Disable all sessions
    await hass.services.async_call(DOMAIN, SERVICE_DISABLE_MAINTENANCE, {}, blocking=True)
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


async def test_disable_session_on_one_of_several_instances(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
    mock_auth_info: LogShedAuthInfo,
) -> None:
    """Test a session ID unknown to other instances still ends where it exists."""
    await setup_integration(hass, mock_config_entry, mock_api_client)
    second_entry, second_client = _second_instance(mock_api_client, mock_auth_info)
    await setup_integration(hass, second_entry, second_client)

    mock_api_client.async_disable_maintenance = AsyncMock(side_effect=LogShedNotFound("unknown"))
    await hass.services.async_call(
        DOMAIN, SERVICE_DISABLE_MAINTENANCE, {"session_id": "sess-456"}, blocking=True
    )
    second_client.async_disable_maintenance.assert_awaited_once_with(session_id="sess-456")

    # Unknown everywhere is an error
    second_client.async_disable_maintenance = AsyncMock(side_effect=LogShedNotFound("unknown"))
    with pytest.raises(HomeAssistantError, match="Failed to disable maintenance window"):
        await hass.services.async_call(
            DOMAIN, SERVICE_DISABLE_MAINTENANCE, {"session_id": "nope"}, blocking=True
        )
