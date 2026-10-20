"""Update platform for the LogShed integration."""

from __future__ import annotations

from homeassistant.components.update import UpdateEntity, UpdateEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import (
    LogShedConfigEntry,
    LogShedDataUpdateCoordinator,
    LogShedVersionCoordinator,
)
from .entity import logshed_device_info

RELEASE_URL = "https://github.com/logshed/logshed/releases/tag/v{version}"

UPDATE_DESCRIPTION = UpdateEntityDescription(
    key="update",
    translation_key="update",
    # Read only (no install), so Diagnostic as Home Assistant uses without a description
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LogShedConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the LogShed update entity based on a config entry."""
    runtime = entry.runtime_data
    if runtime.version_coordinator is None:
        return
    async_add_entities(
        [LogShedUpdateEntity(runtime.version_coordinator, runtime.coordinator, UPDATE_DESCRIPTION)]
    )


class LogShedUpdateEntity(CoordinatorEntity[LogShedVersionCoordinator], UpdateEntity):
    """Shows when a newer stable LogShed release is available (no install support)."""

    _attr_has_entity_name = True
    entity_description: UpdateEntityDescription

    def __init__(
        self,
        coordinator: LogShedVersionCoordinator,
        metrics_coordinator: LogShedDataUpdateCoordinator,
        description: UpdateEntityDescription,
    ) -> None:
        """Initialize the update entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._metrics_coordinator = metrics_coordinator
        self._attr_unique_id = f"{metrics_coordinator.data.instance_id}_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Attach the entity to the LogShed device created by the other platforms."""
        return logshed_device_info(self._metrics_coordinator)

    @property
    def installed_version(self) -> str | None:
        """Return the running LogShed version."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.current_version or None

    @property
    def latest_version(self) -> str | None:
        """Return the latest stable release, or None when the check is off or failed."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.latest_version

    @property
    def release_url(self) -> str | None:
        """Return the GitHub release page of the latest version."""
        if not (latest := self.latest_version):
            return None
        return RELEASE_URL.format(version=latest)

    def version_is_newer(self, latest_version: str, installed_version: str) -> bool:
        """Use LogShed's own comparison, which treats pre-releases like LogShed does."""
        return bool(self.coordinator.data and self.coordinator.data.update_available)
