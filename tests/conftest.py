"""Test configuration and fixtures for LogShed integration tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

try:
    import pycares

    pycares.Channel()
except Exception:
    pass


from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant

from custom_components.logshed.api import LogShedApiClient, LogShedAuthInfo, LogShedMetrics
from custom_components.logshed.const import (
    CONF_API_TOKEN,
    CONF_MAINTENANCE_DURATION,
    CONF_MAINTENANCE_LOG_HANDLING,
    CONF_SCAN_INTERVAL,
    CONF_VERIFY_SSL,
    DOMAIN,
    PLATFORMS,
)

MOCK_HOST = "http://192.168.1.100:8000"
MOCK_TOKEN = "ls_live_testsecrettoken123456789"
MOCK_INSTANCE_ID = "12345678-1234-5678-1234-567812345678"
MOCK_SESSION_UNTIL = "2099-01-01T00:00:00+00:00"

MOCK_AUTH_VERIFY_RESPONSE: dict[str, Any] = {
    "valid": True,
    "name": "HA Integration Token",
    "scopes": ["*"],
    "expires_at": None,
}

MOCK_SYSTEM_METRICS_RESPONSE: dict[str, Any] = {
    "status": "ok",
    "version": "1.3.0",
    "instance_id": MOCK_INSTANCE_ID,
    "server_name": "LogShed",
    "ingest_rate": 42.5,
    "error_count_24h": 17,
    "error_count_1h": 3,
    "severity_counts_24h": {
        "emergency": 0,
        "alert": 1,
        "critical": 4,
        "error": 12,
        "warning": 23,
    },
    "top_error_breakdown": {
        "top_apps": [
            {"name": "postgres", "count": 12},
            {"name": "traefik", "count": 5},
        ],
        "top_hosts": [
            {"name": "compute-01", "count": 14},
            {"name": "nas", "count": 3},
        ],
    },
    "alert_state": {
        "active": True,
        "recent_firing_count": 2,
        "last_triggered_at": "2026-10-15T14:30:00Z",
        "last_rule_name": "Critical Error Spike",
    },
    "queue_depth": 5,
    "dropped_logs": 10,
    "dropped_by_filter": 25,
    "udp_receive_errors": 7,
    "db_size_bytes": 104857600,
    "total_logs_count": 500000,
    "disk_free_bytes": 107374182400,  # 100 GB
    "disk_total_bytes": 214748364800,  # 200 GB
    "disk_used_percent": 50.0,
    "maintenance": {
        "active": True,
        "until": "2026-10-15T16:00:00Z",
        "remaining_seconds": 1800,
        "active_sessions_count": 1,
        "log_handling": "silence_alerts",
    },
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests."""
    yield


@pytest.fixture
def mock_metrics() -> LogShedMetrics:
    """Fixture for parsed LogShedMetrics."""
    return LogShedMetrics.from_dict(MOCK_SYSTEM_METRICS_RESPONSE)


@pytest.fixture
def mock_auth_info() -> LogShedAuthInfo:
    """Fixture for parsed LogShedAuthInfo."""
    return LogShedAuthInfo(
        valid=True,
        name="HA Integration Token",
        scopes=["*"],
        expires_at=None,
    )


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Fixture for a LogShed MockConfigEntry."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=MOCK_INSTANCE_ID,
        title="LogShed (LogShed)",
        data={
            CONF_HOST: MOCK_HOST,
            CONF_API_TOKEN: MOCK_TOKEN,
            CONF_VERIFY_SSL: True,
        },
        options={
            CONF_SCAN_INTERVAL: 30,
            CONF_MAINTENANCE_DURATION: 60,
            CONF_MAINTENANCE_LOG_HANDLING: "silence_alerts",
        },
    )


@pytest.fixture
def mock_api_client(
    mock_auth_info: LogShedAuthInfo, mock_metrics: LogShedMetrics
) -> LogShedApiClient:
    """Fixture for a mocked LogShedApiClient."""
    client = LogShedApiClient(
        host=MOCK_HOST,
        api_token=MOCK_TOKEN,
        session=AsyncMock(),
        verify_ssl=True,
    )
    client.async_verify_auth = AsyncMock(return_value=mock_auth_info)
    client.async_get_system_metrics = AsyncMock(return_value=mock_metrics)
    client.async_enable_maintenance = AsyncMock(
        return_value={"session_id": "sess-123", "active": True, "until": MOCK_SESSION_UNTIL}
    )
    client.async_disable_maintenance = AsyncMock(
        return_value={"active": False, "terminated_sessions": 1}
    )
    client.async_trigger_prune = AsyncMock(return_value={"status": "ok", "deleted_logs": 150})
    client.async_trigger_vacuum = AsyncMock(
        return_value={"status": "ok", "reclaimed_bytes": 20971520}
    )
    return client


async def setup_integration(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    client: LogShedApiClient,
    platforms: list[Platform] | None = None,
) -> None:
    """Set up the LogShed config entry with a mocked API client."""
    entry.add_to_hass(hass)
    with (
        patch("custom_components.logshed.LogShedApiClient", return_value=client),
        patch("custom_components.logshed.PLATFORMS", platforms or PLATFORMS),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
