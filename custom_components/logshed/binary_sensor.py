"""Binary sensor platform for the LogShed integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import LogShedMetrics
from .const import DOMAIN
from .coordinator import LogShedDataUpdateCoordinator
from .entity import LogShedEntity


@dataclass(frozen=True, kw_only=True)
class LogShedBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes LogShed binary sensor entity."""

    is_on_fn: Callable[[LogShedDataUpdateCoordinator], bool | None]
    extra_attrs_fn: Callable[[LogShedMetrics], dict[str, Any]] | None = None


BINARY_SENSOR_DESCRIPTIONS: tuple[LogShedBinarySensorEntityDescription, ...] = (
    LogShedBinarySensorEntityDescription(
        key="alert_state",
        translation_key="alert_state",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:bell-alert",
        is_on_fn=lambda coordinator: coordinator.data.alert_active if coordinator.data else None,
        extra_attrs_fn=lambda metrics: {
            "recent_firing_count": metrics.alert_recent_firing_count,
            "last_rule_name": metrics.alert_last_rule_name,
            "last_triggered_at": metrics.alert_last_triggered_at,
        },
    ),
    LogShedBinarySensorEntityDescription(
        key="maintenance_active",
        translation_key="maintenance_active",
        device_class=None,
        icon="mdi:wrench-clock",
        is_on_fn=lambda coordinator: (
            coordinator.data.maintenance_active if coordinator.data else None
        ),
        extra_attrs_fn=lambda metrics: {
            "active_sessions_count": metrics.maintenance_active_sessions_count,
            "log_handling": metrics.maintenance_log_handling,
            "until": metrics.maintenance_until,
        },
    ),
    LogShedBinarySensorEntityDescription(
        key="connectivity",
        translation_key="connectivity",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        icon="mdi:server-network",
        is_on_fn=lambda coordinator: coordinator.last_update_success,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up LogShed binary sensor entities based on a config entry."""
    coordinator: LogShedDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        LogShedBinarySensorEntity(coordinator, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    )


class LogShedBinarySensorEntity(LogShedEntity, BinarySensorEntity):
    """Representation of a LogShed binary sensor."""

    entity_description: LogShedBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: LogShedDataUpdateCoordinator,
        description: LogShedBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        return self.entity_description.is_on_fn(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        if not self.coordinator.data or not self.entity_description.extra_attrs_fn:
            return None
        return self.entity_description.extra_attrs_fn(self.coordinator.data)
