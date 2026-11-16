"""Diagnostics support for the LogShed integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_API_TOKEN
from .coordinator import LogShedConfigEntry

TO_REDACT = {CONF_API_TOKEN}
# Source addresses are the user's network layout; diagnostics end up in public issues
METRICS_TO_REDACT = {"address"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: LogShedConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "scopes": runtime.scopes,
        "last_update_success": coordinator.last_update_success,
        "server_status": coordinator.server_status,
        "upgrade": coordinator.upgrade,
        "metrics": (
            async_redact_data(asdict(coordinator.data), METRICS_TO_REDACT)
            if coordinator.data
            else None
        ),
        "version": (
            asdict(runtime.version_coordinator.data)
            if runtime.version_coordinator and runtime.version_coordinator.data
            else None
        ),
    }
