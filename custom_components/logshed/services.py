"""Service actions for the LogShed integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .api import LogShedConflict
from .const import (
    DOMAIN,
    LOG_HANDLING_DROP_ERRORS,
    LOG_HANDLING_SILENCE_ALERTS,
    SERVICE_DISABLE_MAINTENANCE,
    SERVICE_ENABLE_MAINTENANCE,
)
from .coordinator import LogShedDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

ENABLE_MAINTENANCE_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): cv.string,
        vol.Optional("config_entry_id"): cv.string,
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
        vol.Optional("device_id"): cv.string,
        vol.Optional("config_entry_id"): cv.string,
        vol.Optional("session_id", default=""): cv.string,
    }
)


def _get_target_coordinators(
    hass: HomeAssistant, call: ServiceCall
) -> list[LogShedDataUpdateCoordinator]:
    """Resolve target coordinators from service call data."""
    domain_data: dict[str, LogShedDataUpdateCoordinator] = hass.data.get(DOMAIN, {})
    if not domain_data:
        raise HomeAssistantError("No LogShed integration instances loaded")

    # 1. By config_entry_id
    if config_entry_id := call.data.get("config_entry_id"):
        if coordinator := domain_data.get(config_entry_id):
            return [coordinator]
        raise HomeAssistantError(f"LogShed config entry '{config_entry_id}' not found")

    # 2. By device_id
    if device_id := call.data.get("device_id"):
        dev_reg = dr.async_get(hass)
        device = dev_reg.async_get(device_id)
        if device is None:
            raise HomeAssistantError(f"Device '{device_id}' not found")
        coordinators = [
            domain_data[entry_id] for entry_id in device.config_entries if entry_id in domain_data
        ]
        if coordinators:
            return coordinators
        raise HomeAssistantError(f"No LogShed coordinator found for device '{device_id}'")

    # 3. Default to all loaded LogShed coordinators
    return list(domain_data.values())


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register LogShed integration services."""

    async def handle_enable_maintenance(call: ServiceCall) -> None:
        """Handle enabling maintenance window."""
        coordinators = _get_target_coordinators(hass, call)
        duration_minutes: int = call.data["duration_minutes"]
        reason: str = call.data["reason"]
        log_handling: str = call.data["log_handling"]
        target_app: str | None = call.data.get("target_app") or None
        target_host: str | None = call.data.get("target_host") or None

        for coordinator in coordinators:
            try:
                await coordinator.api.async_enable_maintenance(
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

            await coordinator.async_request_refresh()

    async def handle_disable_maintenance(call: ServiceCall) -> None:
        """Handle disabling maintenance window."""
        coordinators = _get_target_coordinators(hass, call)
        session_id: str | None = call.data.get("session_id") or None

        for coordinator in coordinators:
            try:
                await coordinator.api.async_disable_maintenance(session_id=session_id)
            except Exception as err:
                raise HomeAssistantError(f"Failed to disable maintenance window: {err}") from err

            await coordinator.async_request_refresh()

    if not hass.services.has_service(DOMAIN, SERVICE_ENABLE_MAINTENANCE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_ENABLE_MAINTENANCE,
            handle_enable_maintenance,
            schema=ENABLE_MAINTENANCE_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_DISABLE_MAINTENANCE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_DISABLE_MAINTENANCE,
            handle_disable_maintenance,
            schema=DISABLE_MAINTENANCE_SCHEMA,
        )


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload LogShed integration services."""
    if hass.services.has_service(DOMAIN, SERVICE_ENABLE_MAINTENANCE):
        hass.services.async_remove(DOMAIN, SERVICE_ENABLE_MAINTENANCE)
    if hass.services.has_service(DOMAIN, SERVICE_DISABLE_MAINTENANCE):
        hass.services.async_remove(DOMAIN, SERVICE_DISABLE_MAINTENANCE)
