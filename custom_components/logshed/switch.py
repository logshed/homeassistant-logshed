"""Switch platform for the LogShed integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_MAINTENANCE_DURATION,
    CONF_MAINTENANCE_LOG_HANDLING,
    DEFAULT_MAINTENANCE_DURATION,
    DEFAULT_MAINTENANCE_LOG_HANDLING,
    DOMAIN,
)
from .coordinator import LogShedDataUpdateCoordinator
from .entity import LogShedEntity

SWITCH_DESCRIPTION = SwitchEntityDescription(
    key="maintenance_mode",
    translation_key="maintenance_mode",
    icon="mdi:wrench",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up LogShed switch entity based on a config entry."""
    coordinator: LogShedDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([LogShedMaintenanceSwitch(coordinator, SWITCH_DESCRIPTION)])


class LogShedMaintenanceSwitch(LogShedEntity, SwitchEntity):
    """Switch to toggle LogShed maintenance mode."""

    entity_description: SwitchEntityDescription

    def __init__(
        self,
        coordinator: LogShedDataUpdateCoordinator,
        description: SwitchEntityDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return True if maintenance mode is active."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.maintenance_active

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on maintenance mode."""
        options = self.coordinator.config_entry.options
        data = self.coordinator.config_entry.data
        duration = int(
            options.get(
                CONF_MAINTENANCE_DURATION,
                data.get(CONF_MAINTENANCE_DURATION, DEFAULT_MAINTENANCE_DURATION),
            )
        )
        log_handling = options.get(
            CONF_MAINTENANCE_LOG_HANDLING,
            data.get(CONF_MAINTENANCE_LOG_HANDLING, DEFAULT_MAINTENANCE_LOG_HANDLING),
        )

        await self.coordinator.api.async_enable_maintenance(
            duration_minutes=duration,
            reason="Home Assistant maintenance switch",
            log_handling=log_handling,
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off maintenance mode."""
        await self.coordinator.api.async_disable_maintenance()
        await self.coordinator.async_request_refresh()
