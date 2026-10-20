"""Tests for LogShed async API client."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
import pytest

from custom_components.logshed.api import (
    LogShedApiClient,
    LogShedBadRequest,
    LogShedCannotConnect,
    LogShedConflict,
    LogShedError,
    LogShedInvalidAuth,
    LogShedMetrics,
    LogShedNotFound,
    LogShedOperationTimeout,
    LogShedRateLimited,
    LogShedServerError,
)
from custom_components.logshed.const import DEFAULT_REQUEST_TIMEOUT, LONG_OPERATION_TIMEOUT

from .conftest import (
    MOCK_AUTH_VERIFY_RESPONSE,
    MOCK_HOST,
    MOCK_SYSTEM_METRICS_RESPONSE,
    MOCK_TOKEN,
)


def _mock_response(status: int, json_data: dict | None = None, headers: dict | None = None):
    mock = AsyncMock()
    mock.status = status
    mock.headers = headers or {}
    if json_data is not None:
        mock.json = AsyncMock(return_value=json_data)
    else:
        mock.json = AsyncMock(side_effect=Exception("No JSON"))
    mock.raise_for_status = Mock()
    return mock


async def test_api_verify_auth_success() -> None:
    """Test successful auth verification."""
    session = AsyncMock()
    session.request = AsyncMock(return_value=_mock_response(200, MOCK_AUTH_VERIFY_RESPONSE))

    client = LogShedApiClient(MOCK_HOST, MOCK_TOKEN, session)
    auth_info = await client.async_verify_auth()
    assert auth_info.valid is True
    assert auth_info.name == "HA Integration Token"
    assert "*" in auth_info.scopes


async def test_api_get_system_metrics_success() -> None:
    """Test fetching system metrics."""
    session = AsyncMock()
    session.request = AsyncMock(return_value=_mock_response(200, MOCK_SYSTEM_METRICS_RESPONSE))

    client = LogShedApiClient(MOCK_HOST, MOCK_TOKEN, session)
    metrics = await client.async_get_system_metrics()
    assert metrics.server_name == "LogShed"
    assert metrics.ingest_rate == 42.5
    assert metrics.maintenance_active is True
    assert metrics.emergency_logs_24h == 0
    assert metrics.alert_logs_24h == 1
    assert metrics.critical_logs_24h == 4
    assert metrics.error_logs_24h == 12
    assert metrics.warning_logs_24h == 23


def test_metrics_without_severity_counts_default_to_zero() -> None:
    """Test a metrics payload without severity_counts_24h parses with zero counts."""
    data = {k: v for k, v in MOCK_SYSTEM_METRICS_RESPONSE.items() if k != "severity_counts_24h"}
    metrics = LogShedMetrics.from_dict(data)
    assert metrics.error_count_24h == 17
    assert metrics.emergency_logs_24h == 0
    assert metrics.alert_logs_24h == 0
    assert metrics.critical_logs_24h == 0
    assert metrics.error_logs_24h == 0
    assert metrics.warning_logs_24h == 0


async def test_api_maintenance_enable_and_disable() -> None:
    """Test enable and disable maintenance calls."""
    session = AsyncMock()
    session.request = AsyncMock(return_value=_mock_response(200, {"id": "sess-1", "active": True}))

    client = LogShedApiClient(MOCK_HOST, MOCK_TOKEN, session)
    res_enable = await client.async_enable_maintenance(
        duration_minutes=45,
        reason="Upgrades",
        log_handling="drop_errors",
        target_app="app1",
        target_host="host1",
    )
    assert res_enable["id"] == "sess-1"

    session.request = AsyncMock(
        return_value=_mock_response(200, {"active": False, "terminated_sessions": 1})
    )
    res_disable = await client.async_disable_maintenance(session_id="sess-1")
    assert res_disable["active"] is False


async def test_api_prune_and_vacuum() -> None:
    """Test prune and vacuum operations."""
    session = AsyncMock()
    session.request = AsyncMock(
        return_value=_mock_response(200, {"status": "ok", "deleted_logs": 100})
    )

    client = LogShedApiClient(MOCK_HOST, MOCK_TOKEN, session)
    res_prune = await client.async_trigger_prune()
    assert res_prune["status"] == "ok"

    session.request = AsyncMock(
        return_value=_mock_response(200, {"status": "ok", "reclaimed_bytes": 1024})
    )
    res_vacuum = await client.async_trigger_vacuum()
    assert res_vacuum["status"] == "ok"


async def test_api_error_mappings() -> None:
    """Test HTTP status code mappings to specific LogShed exceptions."""
    session = AsyncMock()
    client = LogShedApiClient(MOCK_HOST, MOCK_TOKEN, session)

    # 401 Invalid Auth
    session.request = AsyncMock(return_value=_mock_response(401, {"detail": "Token revoked"}))
    with pytest.raises(LogShedInvalidAuth, match="Token revoked"):
        await client.async_verify_auth()

    # 409 Conflict
    session.request = AsyncMock(
        return_value=_mock_response(409, {"detail": "Session limit reached"})
    )
    with pytest.raises(LogShedConflict, match="Session limit reached"):
        await client.async_enable_maintenance()

    # 429 Rate Limited with Retry-After
    session.request = AsyncMock(
        return_value=_mock_response(
            429, {"detail": "Cooldown active"}, headers={"Retry-After": "45"}
        )
    )
    with pytest.raises(LogShedRateLimited) as exc_info:
        await client.async_trigger_prune()
    assert exc_info.value.retry_after == 45

    # 400 Bad Request
    session.request = AsyncMock(return_value=_mock_response(400, {"detail": "Disk space too low"}))
    with pytest.raises(LogShedBadRequest, match="Disk space too low"):
        await client.async_trigger_vacuum()

    # 500 Server Error
    session.request = AsyncMock(
        return_value=_mock_response(500, {"detail": "Internal database crash"})
    )
    with pytest.raises(LogShedServerError, match="Internal database crash"):
        await client.async_get_system_metrics()


async def test_api_network_exceptions() -> None:
    """Test network connection error handling in API client."""
    session = AsyncMock()
    client = LogShedApiClient(MOCK_HOST, MOCK_TOKEN, session)

    conn_key = aiohttp.client_reqrep.ConnectionKey(
        host="192.168.1.100",
        port=8000,
        is_ssl=False,
        ssl=None,
        proxy=None,
        proxy_auth=None,
        proxy_headers_hash=None,
    )

    # Timeout
    session.request = AsyncMock(side_effect=TimeoutError())
    with pytest.raises(LogShedCannotConnect, match="Timeout"):
        await client.async_verify_auth()

    # Connection Error
    session.request = AsyncMock(
        side_effect=aiohttp.ClientConnectorError(conn_key, OSError("No route to host"))
    )
    with pytest.raises(LogShedCannotConnect, match="Failed to connect"):
        await client.async_verify_auth()

    # SSL Error
    session.request = AsyncMock(
        side_effect=aiohttp.ClientSSLError(conn_key, OSError("Certificate self-signed"))
    )
    with pytest.raises(LogShedCannotConnect, match="SSL certificate error"):
        await client.async_verify_auth()


async def test_api_client_error_statuses() -> None:
    """Test 404, 422 and other 4xx responses map to specific errors, never network errors."""
    session = AsyncMock()
    client = LogShedApiClient(MOCK_HOST, MOCK_TOKEN, session)

    session.request = AsyncMock(
        return_value=_mock_response(404, {"detail": "No active maintenance session with ID x."})
    )
    with pytest.raises(LogShedNotFound, match="No active maintenance session"):
        await client.async_disable_maintenance(session_id="x")

    session.request = AsyncMock(
        return_value=_mock_response(
            422,
            {
                "detail": [
                    {"loc": ["body", "duration_minutes"], "msg": "Input should be <= 1440"},
                    {"loc": ["body", "reason"], "msg": "String too long"},
                ]
            },
        )
    )
    with pytest.raises(LogShedBadRequest, match="Input should be <= 1440; String too long"):
        await client.async_enable_maintenance(duration_minutes=5000)

    session.request = AsyncMock(return_value=_mock_response(418, {"detail": "Teapot"}))
    with pytest.raises(LogShedError, match="HTTP 418: Teapot") as exc_info:
        await client.async_get_system_metrics()
    assert not isinstance(exc_info.value, LogShedCannotConnect)

    # Body without JSON falls back to a default message
    session.request = AsyncMock(return_value=_mock_response(405))
    with pytest.raises(LogShedError, match="HTTP 405"):
        await client.async_get_system_metrics()


async def test_api_long_operations_use_long_timeout() -> None:
    """Test prune and vacuum wait up to 10 minutes; other requests keep the short timeout."""
    session = AsyncMock()
    session.request = AsyncMock(return_value=_mock_response(200, {"status": "ok"}))
    client = LogShedApiClient(MOCK_HOST, MOCK_TOKEN, session)

    with patch("custom_components.logshed.api.asyncio.timeout", wraps=asyncio.timeout) as timeout:
        await client.async_trigger_prune()
        await client.async_trigger_vacuum()
        await client.async_verify_auth()
    assert [c.args[0] for c in timeout.call_args_list] == [
        LONG_OPERATION_TIMEOUT,
        LONG_OPERATION_TIMEOUT,
        DEFAULT_REQUEST_TIMEOUT,
    ]


async def test_api_long_operation_timeout_may_still_run() -> None:
    """Test a timed-out prune says it may still be running, unlike a normal timeout."""
    session = AsyncMock()
    session.request = AsyncMock(side_effect=TimeoutError())
    client = LogShedApiClient(MOCK_HOST, MOCK_TOKEN, session)

    with pytest.raises(LogShedOperationTimeout, match="may still be running on the server"):
        await client.async_trigger_prune()
    with pytest.raises(LogShedOperationTimeout):
        await client.async_trigger_vacuum()
    with pytest.raises(LogShedCannotConnect, match="Timeout"):
        await client.async_get_system_metrics()


def test_metrics_udp_receive_errors() -> None:
    """Test udp_receive_errors parses as a count and stays None when LogShed sends null."""
    assert LogShedMetrics.from_dict(MOCK_SYSTEM_METRICS_RESPONSE).udp_receive_errors == 7
    data = {**MOCK_SYSTEM_METRICS_RESPONSE, "udp_receive_errors": None}
    assert LogShedMetrics.from_dict(data).udp_receive_errors is None
