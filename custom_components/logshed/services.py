"""Service actions for the LogShed integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import LogShedConflict, LogShedNotFound
from .const import (
    ATTR_CONFIG_ENTRY_ID,
    DOMAIN,
    LOG_HANDLING_DROP_ERRORS,
    LOG_HANDLING_SILENCE_ALERTS,
    SCOPE_MAINTENANCE_WRITE,
    SERVICE_DISABLE_MAINTENANCE,
    SERVICE_ENABLE_MAINTENANCE,
)
from .coordinator import LogShedConfigEntry

_LOGGER = logging.getLogger(__name__)

ENABLE_MAINTENANCE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional("duration_minutes", default=30): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=1440)
        ),
        vol.Optional("reason", default="Home Assistant automation"): vol.All(
            cv.string, vol.Length(max=255)
        ),
        vol.Optional("log_handling", default=LOG_HANDLING_SILENCE_ALERTS): vol.In(
            [LOG_HANDLING_SILENCE_ALERTS, LOG_HANDLING_DROP_ERRORS]
        ),
        vol.Optional("target_app", default=""): cv.string,
        vol.Optional("target_host", default=""): cv.string,
    }
)

DISABLE_MAINTENANCE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional("session_id", default=""): cv.string,
    }
)


def _get_target_entries(hass: HomeAssistant, call: ServiceCall) -> list[LogShedConfigEntry]:
    """Resolve the target config entries and check their tokens can manage maintenance.

    Without a config_entry_id, every loaded LogShed instance is targeted.
    """
    if config_entry_id := call.data.get(ATTR_CONFIG_ENTRY_ID):
        entry = hass.config_entries.async_get_entry(config_entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError(f"LogShed config entry '{config_entry_id}' not found")
        if entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError(f"LogShed instance '{entry.title}' is not loaded")
        entries: list[LogShedConfigEntry] = [entry]
    else:
        entries = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
        ]
        if not entries:
            raise ServiceValidationError("No LogShed instances are loaded")

    # Check every target first, so a call never applies to only some instances.
    for entry in entries:
        if not entry.runtime_data.has_scope(SCOPE_MAINTENANCE_WRITE):
            raise ServiceValidationError(
                f"The API token for '{entry.title}' lacks the '{SCOPE_MAINTENANCE_WRITE}' scope"
            )
    return entries


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register LogShed integration services."""

    async def handle_enable_maintenance(call: ServiceCall) -> ServiceResponse:
        """Handle enabling maintenance window."""
        entries = _get_target_entries(hass, call)
        duration_minutes: int = call.data["duration_minutes"]
        reason: str = call.data["reason"]
        log_handling: str = call.data["log_handling"]
        target_app: str | None = call.data.get("target_app") or None
        target_host: str | None = call.data.get("target_host") or None

        sessions: list[dict[str, str | None]] = []
        for entry in entries:
            coordinator = entry.runtime_data.coordinator
            try:
                result = await coordinator.api.async_enable_maintenance(
                    duration_minutes=duration_minutes,
                    reason=reason,
                    log_handling=log_handling,
                    target_app=target_app,
                    target_host=target_host,
                )
            except LogShedConflict as err:
                raise HomeAssistantError(
                    "Maximum active maintenance sessions limit (20) reached"
                ) from err
            except Exception as err:
                raise HomeAssistantError(f"Failed to enable maintenance window: {err}") from err

            sessions.append(
                {
                    "config_entry_id": entry.entry_id,
                    "session_id": result.get("session_id"),
                    "until": result.get("until"),
                }
            )
            await coordinator.async_request_refresh()

        if call.return_response:
            return {"sessions": sessions}
        return None

    async def handle_disable_maintenance(call: ServiceCall) -> None:
        """Handle disabling maintenance window."""
        entries = _get_target_entries(hass, call)
        session_id: str | None = call.data.get("session_id") or None

        # A session ID belongs to one instance, so the others answer 404.
        not_found: list[LogShedNotFound] = []
        for entry in entries:
            coordinator = entry.runtime_data.coordinator
            try:
                await coordinator.api.async_disable_maintenance(session_id=session_id)
            except LogShedNotFound as err:
                not_found.append(err)
                continue
            except Exception as err:
                raise HomeAssistantError(f"Failed to disable maintenance window: {err}") from err

            await coordinator.async_request_refresh()

        if not_found and len(not_found) == len(entries):
            raise HomeAssistantError(
                f"Failed to disable maintenance window: {not_found[0]}"
            ) from not_found[0]

    hass.services.async_register(
        DOMAIN,
        SERVICE_ENABLE_MAINTENANCE,
        handle_enable_maintenance,
        schema=ENABLE_MAINTENANCE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DISABLE_MAINTENANCE,
        handle_disable_maintenance,
        schema=DISABLE_MAINTENANCE_SCHEMA,
    )
