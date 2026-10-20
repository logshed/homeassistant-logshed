"""DataUpdateCoordinator for LogShed integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    LogShedApiClient,
    LogShedCannotConnect,
    LogShedInvalidAuth,
    LogShedMetrics,
    LogShedNotFound,
    LogShedVersion,
    has_scope,
)
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN, VERSION_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


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
            return await self.api.async_get_system_metrics()
        except LogShedInvalidAuth as err:
            raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
        except LogShedCannotConnect as err:
            raise UpdateFailed(f"Cannot connect to LogShed: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error communicating with LogShed: {err}") from err


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
        except Exception as err:
            raise UpdateFailed(f"Unexpected error communicating with LogShed: {err}") from err
