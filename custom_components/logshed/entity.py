"""Base entity for the LogShed integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import LogShedDataUpdateCoordinator


def logshed_device_info(coordinator: LogShedDataUpdateCoordinator) -> DeviceInfo:
    """Return device information about a LogShed instance."""
    return DeviceInfo(
        identifiers={(DOMAIN, coordinator.data.instance_id)},
        name=coordinator.data.server_name or "LogShed",
        manufacturer="LogShed",
        model="Log Management Server",
        sw_version=coordinator.data.version,
        configuration_url=coordinator.api.host,
    )


class LogShedEntity(CoordinatorEntity[LogShedDataUpdateCoordinator]):
    """Base entity for LogShed entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LogShedDataUpdateCoordinator,
        key: str,
    ) -> None:
        """Initialize the LogShed entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.data.instance_id}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this LogShed instance."""
        return logshed_device_info(self.coordinator)
