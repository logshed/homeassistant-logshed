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
    LogShedHealth,
    LogShedInvalidAuth,
    LogShedMetrics,
    LogShedServerError,
)
from custom_components.logshed.const import (
    CONF_API_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_VERIFY_SSL,
    DOMAIN,
)
from custom_components.logshed.coordinator import (
    SERVER_ERROR,
    SERVER_RECOVERY,
    SERVER_RUNNING,
    SERVER_UNREACHABLE,
    SERVER_UPGRADING,
    LogShedDataUpdateCoordinator,
    LogShedVersionCoordinator,
)

from .conftest import (
    MOCK_HEALTH_UPGRADING_RESPONSE,
    MOCK_HOST,
    MOCK_INSTANCE_ID,
    MOCK_SYSTEM_METRICS_RESPONSE,
    MOCK_TOKEN,
)


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


async def test_coordinator_server_error_is_not_unexpected(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """A LogShed error becomes UpdateFailed with its own message, not "Unexpected error"."""
    mock_api_client.async_get_system_metrics = AsyncMock(
        side_effect=LogShedServerError("Internal database crash")
    )
    mock_api_client.async_get_version = AsyncMock(
        side_effect=LogShedServerError("Internal database crash")
    )
    mock_api_client.async_get_health = AsyncMock(
        return_value=LogShedHealth.from_dict({"status": "ok"})
    )
    coordinator = LogShedDataUpdateCoordinator(hass, mock_api_client, mock_config_entry)
    version_coordinator = LogShedVersionCoordinator(hass, mock_api_client, mock_config_entry)

    for coord in (coordinator, version_coordinator):
        with pytest.raises(
            UpdateFailed, match="LogShed error: Internal database crash"
        ) as exc_info:
            await coord._async_update_data()
        assert "Unexpected" not in str(exc_info.value)


async def test_coordinator_lets_bugs_through(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """A bug is not turned into a one-line UpdateFailed, so Home Assistant logs its traceback."""
    mock_api_client.async_get_system_metrics = AsyncMock(side_effect=KeyError("version"))
    mock_api_client.async_get_version = AsyncMock(side_effect=KeyError("version"))
    coordinator = LogShedDataUpdateCoordinator(hass, mock_api_client, mock_config_entry)
    version_coordinator = LogShedVersionCoordinator(hass, mock_api_client, mock_config_entry)

    for coord in (coordinator, version_coordinator):
        with pytest.raises(KeyError):
            await coord._async_update_data()


@pytest.mark.parametrize(
    ("health", "expected_status", "message"),
    [
        (MOCK_HEALTH_UPGRADING_RESPONSE, SERVER_UPGRADING, "LogShed is upgrading its database"),
        (
            {**MOCK_HEALTH_UPGRADING_RESPONSE, "status": "migration_failed"},
            SERVER_RECOVERY,
            "recovery mode after a failed database upgrade",
        ),
    ],
)
async def test_coordinator_reads_upgrade_status_from_health(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
    health: dict,
    expected_status: str,
    message: str,
) -> None:
    """LogShed's 503 while it upgrades or waits in recovery is told apart through /api/health."""
    coordinator = LogShedDataUpdateCoordinator(hass, mock_api_client, mock_config_entry)
    mock_api_client.async_get_system_metrics = AsyncMock(
        side_effect=LogShedCannotConnect("LogShed is upgrading its database.", status=503)
    )
    mock_api_client.async_get_health = AsyncMock(return_value=LogShedHealth.from_dict(health))

    with pytest.raises(UpdateFailed, match=message):
        await coordinator._async_update_data()
    assert coordinator.server_status == expected_status
    assert coordinator.upgrade == MOCK_HEALTH_UPGRADING_RESPONSE["upgrade"]

    # Back to running, without progress, once metrics answer again
    mock_api_client.async_get_system_metrics = AsyncMock(
        return_value=LogShedMetrics.from_dict(MOCK_SYSTEM_METRICS_RESPONSE)
    )
    await coordinator._async_update_data()
    assert coordinator.server_status == SERVER_RUNNING
    assert coordinator.upgrade is None


async def test_coordinator_network_failure_is_unreachable_without_health_request(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """A network failure means unreachable; asking /api/health would only wait out a second timeout."""
    coordinator = LogShedDataUpdateCoordinator(hass, mock_api_client, mock_config_entry)
    mock_api_client.async_get_system_metrics = AsyncMock(
        side_effect=LogShedCannotConnect("Timeout connecting to LogShed")
    )
    mock_api_client.async_get_health = AsyncMock()

    with pytest.raises(UpdateFailed, match="Cannot connect to LogShed: Timeout"):
        await coordinator._async_update_data()
    assert coordinator.server_status == SERVER_UNREACHABLE
    mock_api_client.async_get_health.assert_not_called()


async def test_coordinator_proxy_error_with_health_unreachable(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """A proxy's 502 while LogShed restarts, with /api/health also failing, is unreachable."""
    coordinator = LogShedDataUpdateCoordinator(hass, mock_api_client, mock_config_entry)
    proxy_error = LogShedCannotConnect("LogShed returned 502 (it may be restarting)", status=502)
    mock_api_client.async_get_system_metrics = AsyncMock(side_effect=proxy_error)
    mock_api_client.async_get_health = AsyncMock(side_effect=proxy_error)

    with pytest.raises(UpdateFailed, match="Cannot connect to LogShed: LogShed returned 502"):
        await coordinator._async_update_data()
    assert coordinator.server_status == SERVER_UNREACHABLE


async def test_coordinator_server_error_with_healthy_server_is_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """A 500 from the metrics while LogShed's health is fine is an error, not unreachable."""
    coordinator = LogShedDataUpdateCoordinator(hass, mock_api_client, mock_config_entry)
    mock_api_client.async_get_system_metrics = AsyncMock(
        side_effect=LogShedServerError("Internal database crash")
    )
    mock_api_client.async_get_health = AsyncMock(
        return_value=LogShedHealth.from_dict({"status": "ok"})
    )

    with pytest.raises(UpdateFailed, match="LogShed error: Internal database crash"):
        await coordinator._async_update_data()
    assert coordinator.server_status == SERVER_ERROR
    assert coordinator.upgrade is None


async def test_coordinator_degraded_health_is_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """LogShed's health check answering 503 (its database check failed) means error, not unreachable."""
    coordinator = LogShedDataUpdateCoordinator(hass, mock_api_client, mock_config_entry)
    mock_api_client.async_get_system_metrics = AsyncMock(
        side_effect=LogShedServerError("database is locked")
    )
    mock_api_client.async_get_health = AsyncMock(
        side_effect=LogShedCannotConnect("LogShed returned 503 (it may be restarting)", status=503)
    )

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.server_status == SERVER_ERROR


async def test_coordinator_refused_token_is_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """A refused token does not leave Server Status at running."""
    coordinator = LogShedDataUpdateCoordinator(hass, mock_api_client, mock_config_entry)
    mock_api_client.async_get_system_metrics = AsyncMock(
        side_effect=LogShedInvalidAuth("Token revoked")
    )

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()
    assert coordinator.server_status == SERVER_ERROR


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
