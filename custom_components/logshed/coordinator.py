"""DataUpdateCoordinator for LogShed integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, NoReturn

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    LogShedApiClient,
    LogShedCannotConnect,
    LogShedError,
    LogShedInvalidAuth,
    LogShedMetrics,
    LogShedNotFound,
    LogShedVersion,
    has_scope,
)
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN, VERSION_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

# The Server Status sensor's states
SERVER_RUNNING = "running"
SERVER_UPGRADING = "upgrading"
SERVER_RECOVERY = "recovery"
SERVER_ERROR = "error"
SERVER_UNREACHABLE = "unreachable"
SERVER_STATUSES = [
    SERVER_RUNNING,
    SERVER_UPGRADING,
    SERVER_RECOVERY,
    SERVER_ERROR,
    SERVER_UNREACHABLE,
]


@dataclass
class LogShedRuntimeData:
    """Runtime data stored on a LogShed config entry."""

    coordinator: LogShedDataUpdateCoordinator
    scopes: list[str]
    # None when the LogShed server has no /api/v1/system/version endpoint
    version_coordinator: LogShedVersionCoordinator | None = None

    def has_scope(self, scope: str) -> bool:
        """Return True if the entry's API token grants the scope."""
        return has_scope(self.scopes, scope)


type LogShedConfigEntry = ConfigEntry[LogShedRuntimeData]


class LogShedDataUpdateCoordinator(DataUpdateCoordinator[LogShedMetrics]):
    """Class to manage fetching LogShed data from the API."""

    config_entry: LogShedConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        api: LogShedApiClient,
        entry: LogShedConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.api = api
        self.config_entry = entry
        # Whether LogShed is running, upgrading its database, in recovery or not answering;
        # read from /api/health when the metrics request fails
        self.server_status = SERVER_RUNNING
        # The upgrade stage and progress while upgrading or in recovery
        self.upgrade: dict[str, Any] | None = None

        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> LogShedMetrics:
        """Fetch data from LogShed API."""
        try:
            metrics = await self.api.async_get_system_metrics()
        except LogShedInvalidAuth as err:
            # LogShed answers, but refuses the token: Home Assistant asks for a new one
            self._set_server_status(SERVER_ERROR)
            raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
        except LogShedCannotConnect as err:
            # A network failure needs no second request; an HTTP answer may come from
            # LogShed itself while it upgrades its database
            if err.status is None:
                self._set_server_status(SERVER_UNREACHABLE)
            else:
                await self._read_server_status(SERVER_UNREACHABLE)
            self._raise_for_server_status(f"Cannot connect to LogShed: {err}", err)
        except LogShedError as err:
            await self._read_server_status(SERVER_ERROR)
            self._raise_for_server_status(f"LogShed error: {err}", err)
        self._set_server_status(SERVER_RUNNING)
        return metrics

    def _set_server_status(self, status: str, upgrade: dict[str, Any] | None = None) -> None:
        changed = (status, upgrade) != (self.server_status, self.upgrade)
        self.server_status = status
        self.upgrade = upgrade
        # The coordinator updates entities only when a poll's success changes, so between two
        # failed polls a new status or upgrade progress would not reach them otherwise
        if changed and not self.last_update_success and status != SERVER_RUNNING:
            self.async_update_listeners()

    async def _read_server_status(self, otherwise: str) -> None:
        """Ask /api/health whether LogShed is upgrading or in recovery; otherwise is the status else."""
        try:
            health = await self.api.async_get_health()
        except LogShedCannotConnect as err:
            # LogShed's own health check answers 503 when its database check fails; a gateway's
            # 503 after a metrics failure that already means unreachable stays unreachable
            self._set_server_status(otherwise if err.status == 503 else SERVER_UNREACHABLE)
            return
        except LogShedError:
            self._set_server_status(otherwise)
            return
        if health.status == "upgrading":
            self._set_server_status(SERVER_UPGRADING, health.upgrade)
        elif health.status == "migration_failed":
            self._set_server_status(SERVER_RECOVERY, health.upgrade)
        else:
            self._set_server_status(otherwise)

    def _raise_for_server_status(self, message: str, err: LogShedError) -> NoReturn:
        if self.server_status == SERVER_UPGRADING:
            message = "LogShed is upgrading its database"
        elif self.server_status == SERVER_RECOVERY:
            message = (
                "LogShed is in recovery mode after a failed database upgrade: "
                "open its web UI to retry"
            )
        raise UpdateFailed(message) from err


class LogShedVersionCoordinator(DataUpdateCoordinator[LogShedVersion]):
    """Class to poll the LogShed version and update status once an hour."""

    config_entry: LogShedConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        api: LogShedApiClient,
        entry: LogShedConfigEntry,
    ) -> None:
        """Initialize the version coordinator."""
        self.api = api
        self.config_entry = entry
        # Set when the server answers 404, i.e. it predates the version endpoint
        self.endpoint_missing = False
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}_version",
            update_interval=timedelta(seconds=VERSION_SCAN_INTERVAL),
        )

    async def _async_update_data(self) -> LogShedVersion:
        """Fetch version information from LogShed API."""
        try:
            return await self.api.async_get_version()
        except LogShedNotFound as err:
            self.endpoint_missing = True
            raise UpdateFailed("LogShed does not provide /api/v1/system/version") from err
        except LogShedInvalidAuth as err:
            raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
        except LogShedCannotConnect as err:
            raise UpdateFailed(f"Cannot connect to LogShed: {err}") from err
        except LogShedError as err:
            raise UpdateFailed(f"LogShed error: {err}") from err
