"""DataUpdateCoordinator for LogShed integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import LogShedApiClient, LogShedCannotConnect, LogShedInvalidAuth, LogShedMetrics
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class LogShedDataUpdateCoordinator(DataUpdateCoordinator[LogShedMetrics]):
    """Class to manage fetching LogShed data from the API."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        api: LogShedApiClient,
        entry: ConfigEntry,
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
