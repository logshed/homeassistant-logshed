"""Button platform for the LogShed integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import LogShedBadRequest, LogShedConflict, LogShedRateLimited
from .const import DOMAIN
from .coordinator import LogShedDataUpdateCoordinator
from .entity import LogShedEntity

PRUNE_BUTTON_DESCRIPTION = ButtonEntityDescription(
    key="prune_database",
    translation_key="prune_database",
    icon="mdi:content-cut",
    entity_category=EntityCategory.DIAGNOSTIC,
)

VACUUM_BUTTON_DESCRIPTION = ButtonEntityDescription(
    key="vacuum_database",
    translation_key="vacuum_database",
    icon="mdi:database-sync",
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up LogShed button entities based on a config entry."""
    coordinator: LogShedDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            LogShedPruneButton(coordinator, PRUNE_BUTTON_DESCRIPTION),
            LogShedVacuumButton(coordinator, VACUUM_BUTTON_DESCRIPTION),
        ]
    )


class LogShedPruneButton(LogShedEntity, ButtonEntity):
    """Button to trigger retention pruning and compaction."""

    entity_description: ButtonEntityDescription

    def __init__(
        self,
        coordinator: LogShedDataUpdateCoordinator,
        description: ButtonEntityDescription,
    ) -> None:
        """Initialize the prune button."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        """Trigger database prune."""
        try:
            await self.coordinator.api.async_trigger_prune()
        except LogShedConflict as err:
            raise HomeAssistantError(
                "A prune or compaction operation is already in progress"
            ) from err
        except LogShedRateLimited as err:
            seconds_str = f"{err.retry_after} seconds" if err.retry_after else "a short period"
            raise HomeAssistantError(f"Prune cooldown active, retry in {seconds_str}") from err
        except Exception as err:
            raise HomeAssistantError(f"Prune operation failed: {err}") from err

        await self.coordinator.async_request_refresh()


class LogShedVacuumButton(LogShedEntity, ButtonEntity):
    """Button to trigger database VACUUM operation."""

    entity_description: ButtonEntityDescription

    def __init__(
        self,
        coordinator: LogShedDataUpdateCoordinator,
        description: ButtonEntityDescription,
    ) -> None:
        """Initialize the vacuum button."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        """Trigger database vacuum."""
        try:
            await self.coordinator.api.async_trigger_vacuum()
        except LogShedConflict as err:
            raise HomeAssistantError(
                "A prune or compaction operation is already in progress"
            ) from err
        except LogShedBadRequest as err:
            raise HomeAssistantError("Insufficient disk space for VACUUM") from err
        except LogShedRateLimited as err:
            seconds_str = f"{err.retry_after} seconds" if err.retry_after else "a short period"
            raise HomeAssistantError(f"Vacuum cooldown active, retry in {seconds_str}") from err
        except Exception as err:
            raise HomeAssistantError(f"Vacuum operation failed: {err}") from err

        await self.coordinator.async_request_refresh()
