"""Tests for LogShed async API client."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import aiohttp
import pytest

from custom_components.logshed.api import (
    LogShedApiClient,
    LogShedBadRequest,
    LogShedCannotConnect,
    LogShedConflict,
    LogShedInvalidAuth,
    LogShedRateLimited,
    LogShedServerError,
)

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
    assert metrics.server_name == "TestShed"
    assert metrics.ingest_rate == 42.5
    assert metrics.maintenance_active is True


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
