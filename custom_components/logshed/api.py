"""Asynchronous API client for the LogShed REST API."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import aiohttp
from homeassistant.exceptions import HomeAssistantError

from .const import (
    ENDPOINT_AUTH_VERIFY,
    ENDPOINT_MAINTENANCE_DISABLE,
    ENDPOINT_MAINTENANCE_ENABLE,
    ENDPOINT_SYSTEM_METRICS,
    ENDPOINT_SYSTEM_PRUNE,
    ENDPOINT_SYSTEM_VACUUM,
)

_LOGGER = logging.getLogger(__name__)


class LogShedError(HomeAssistantError):
    """Base exception for LogShed errors."""


class LogShedCannotConnect(LogShedError):
    """Exception raised when unable to connect to LogShed."""


class LogShedInvalidAuth(LogShedError):
    """Exception raised when authentication fails or scopes are insufficient."""


class LogShedConflict(LogShedError):
    """Exception raised when an operation conflicts with existing server state (409)."""


class LogShedRateLimited(LogShedError):
    """Exception raised when an operation is rate limited or in cooldown (429)."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class LogShedBadRequest(LogShedError):
    """Exception raised when a bad request is submitted (400)."""


class LogShedServerError(LogShedError):
    """Exception raised on server internal error (500)."""


@dataclass
class LogShedAuthInfo:
    """Information returned from /api/v1/auth/verify."""

    valid: bool
    name: str
    scopes: list[str]
    expires_at: str | None


@dataclass
class LogShedMetrics:
    """Parsed system metrics from /api/v1/system/metrics."""

    instance_id: str
    server_name: str
    version: str
    ingest_rate: float
    error_count_24h: int
    error_count_1h: int
    top_error_apps: list[dict[str, Any]]
    top_error_hosts: list[dict[str, Any]]
    alert_active: bool
    alert_recent_firing_count: int
    alert_last_triggered_at: str | None
    alert_last_rule_name: str | None
    queue_depth: int
    dropped_logs: int
    dropped_by_filter: int
    db_size_mb: float
    db_size_bytes: int
    total_logs_count: int
    disk_free_bytes: int
    disk_total_bytes: int
    disk_used_percent: float
    maintenance_active: bool
    maintenance_until: str | None
    maintenance_remaining_seconds: int
    maintenance_active_sessions_count: int
    maintenance_log_handling: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LogShedMetrics:
        """Create LogShedMetrics from API response dictionary."""
        top_err = data.get("top_error_breakdown") or {}
        alert = data.get("alert_state") or {}
        maint = data.get("maintenance") or {}

        top_apps = [
            {"name": item.get("name", ""), "count": item.get("count", 0)}
            for item in top_err.get("top_apps", [])
        ]
        top_hosts = [
            {"name": item.get("name", ""), "count": item.get("count", 0)}
            for item in top_err.get("top_hosts", [])
        ]

        return cls(
            instance_id=data.get("instance_id", "00000000-0000-0000-0000-000000000000"),
            server_name=data.get("server_name", "LogShed"),
            version=data.get("version", "1.3.0"),
            ingest_rate=float(data.get("ingest_rate", 0.0)),
            error_count_24h=int(data.get("error_count_24h", 0)),
            error_count_1h=int(data.get("error_count_1h", 0)),
            top_error_apps=top_apps,
            top_error_hosts=top_hosts,
            alert_active=bool(alert.get("active", False)),
            alert_recent_firing_count=int(alert.get("recent_firing_count", 0)),
            alert_last_triggered_at=alert.get("last_triggered_at"),
            alert_last_rule_name=alert.get("last_rule_name"),
            queue_depth=int(data.get("queue_depth", 0)),
            dropped_logs=int(data.get("dropped_logs", 0)),
            dropped_by_filter=int(data.get("dropped_by_filter", 0)),
            db_size_mb=float(data.get("db_size_mb", 0.0)),
            db_size_bytes=int(data.get("db_size_bytes", 0)),
            total_logs_count=int(data.get("total_logs_count", 0)),
            disk_free_bytes=int(data.get("disk_free_bytes", 0)),
            disk_total_bytes=int(data.get("disk_total_bytes", 0)),
            disk_used_percent=float(data.get("disk_used_percent", 0.0)),
            maintenance_active=bool(maint.get("active", False)),
            maintenance_until=maint.get("until"),
            maintenance_remaining_seconds=int(maint.get("remaining_seconds", 0)),
            maintenance_active_sessions_count=int(maint.get("active_sessions_count", 0)),
            maintenance_log_handling=str(maint.get("log_handling", "silence_alerts")),
        )


class LogShedApiClient:
    """API client for connecting to LogShed."""

    def __init__(
        self,
        host: str,
        api_token: str,
        session: aiohttp.ClientSession,
        verify_ssl: bool = True,
    ) -> None:
        """Initialize the LogShed API client."""
        self.host = host.rstrip("/")
        self.api_token = api_token.strip()
        self.session = session
        self.verify_ssl = verify_ssl

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send an asynchronous HTTP request to LogShed."""
        url = f"{self.host}{endpoint}"
        try:
            async with asyncio.timeout(15):
                response = await self.session.request(
                    method=method,
                    url=url,
                    json=json_data,
                    headers=self._headers(),
                    ssl=self.verify_ssl,
                )

                if response.status in (401, 403):
                    error_detail = "Invalid or expired API token"
                    try:
                        body = await response.json()
                        error_detail = body.get("detail", error_detail)
                    except Exception:
                        pass
                    raise LogShedInvalidAuth(error_detail)

                if response.status == 409:
                    error_detail = "Operation conflict"
                    try:
                        body = await response.json()
                        error_detail = body.get("detail", error_detail)
                    except Exception:
                        pass
                    raise LogShedConflict(error_detail)

                if response.status == 429:
                    error_detail = "Too many requests"
                    retry_after = None
                    try:
                        retry_after_hdr = response.headers.get("Retry-After")
                        if retry_after_hdr:
                            retry_after = int(retry_after_hdr)
                        body = await response.json()
                        error_detail = body.get("detail", error_detail)
                    except Exception:
                        pass
                    raise LogShedRateLimited(error_detail, retry_after=retry_after)

                if response.status == 400:
                    error_detail = "Bad request"
                    try:
                        body = await response.json()
                        error_detail = body.get("detail", error_detail)
                    except Exception:
                        pass
                    raise LogShedBadRequest(error_detail)

                if response.status >= 500:
                    error_detail = f"Server error: {response.status}"
                    try:
                        body = await response.json()
                        error_detail = body.get("detail", error_detail)
                    except Exception:
                        pass
                    raise LogShedServerError(error_detail)

                response.raise_for_status()
                return await response.json()

        except TimeoutError as err:
            raise LogShedCannotConnect(f"Timeout connecting to LogShed at {self.host}") from err
        except aiohttp.ClientSSLError as err:
            raise LogShedCannotConnect(
                f"SSL certificate error connecting to {self.host}: {err}"
            ) from err
        except aiohttp.ClientConnectorError as err:
            raise LogShedCannotConnect(
                f"Failed to connect to LogShed at {self.host}: {err}"
            ) from err
        except aiohttp.ClientError as err:
            raise LogShedCannotConnect(f"Network error communicating with LogShed: {err}") from err

    async def async_verify_auth(self) -> LogShedAuthInfo:
        """Verify token validity and retrieve granted scopes."""
        data = await self._request("GET", ENDPOINT_AUTH_VERIFY)
        return LogShedAuthInfo(
            valid=bool(data.get("valid", False)),
            name=str(data.get("name", "")),
            scopes=list(data.get("scopes", [])),
            expires_at=data.get("expires_at"),
        )

    async def async_get_system_metrics(self) -> LogShedMetrics:
        """Fetch system metrics and telemetry from LogShed."""
        data = await self._request("GET", ENDPOINT_SYSTEM_METRICS)
        return LogShedMetrics.from_dict(data)

    async def async_enable_maintenance(
        self,
        duration_minutes: int = 60,
        reason: str = "Home Assistant automation",
        log_handling: str = "silence_alerts",
        target_app: str | None = None,
        target_host: str | None = None,
    ) -> dict[str, Any]:
        """Start an on-demand maintenance session."""
        payload: dict[str, Any] = {
            "duration_minutes": duration_minutes,
            "reason": reason,
            "log_handling": log_handling,
        }
        if target_app:
            payload["target_app"] = target_app
        if target_host:
            payload["target_host"] = target_host

        return await self._request("POST", ENDPOINT_MAINTENANCE_ENABLE, json_data=payload)

    async def async_disable_maintenance(
        self,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Stop an on-demand maintenance session or all active sessions."""
        payload: dict[str, Any] = {}
        if session_id:
            payload["session_id"] = session_id

        return await self._request("POST", ENDPOINT_MAINTENANCE_DISABLE, json_data=payload)

    async def async_trigger_prune(self) -> dict[str, Any]:
        """Trigger database retention prune and compaction."""
        return await self._request("POST", ENDPOINT_SYSTEM_PRUNE)

    async def async_trigger_vacuum(self) -> dict[str, Any]:
        """Trigger database VACUUM operation."""
        return await self._request("POST", ENDPOINT_SYSTEM_VACUUM)
