"""Sensor platform for the LogShed integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfInformation, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import LogShedMetrics
from .const import DOMAIN
from .coordinator import LogShedDataUpdateCoordinator
from .entity import LogShedEntity


@dataclass(frozen=True, kw_only=True)
class LogShedSensorEntityDescription(SensorEntityDescription):
    """Describes LogShed sensor entity."""

    value_fn: Callable[[LogShedMetrics], Any]
    extra_attrs_fn: Callable[[LogShedMetrics], dict[str, Any]] | None = None


SENSOR_DESCRIPTIONS: tuple[LogShedSensorEntityDescription, ...] = (
    LogShedSensorEntityDescription(
        key="ingestion_rate",
        translation_key="ingestion_rate",
        icon="mdi:chart-line",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="logs/s",
        value_fn=lambda metrics: metrics.ingest_rate,
    ),
    LogShedSensorEntityDescription(
        key="error_count_24h",
        translation_key="error_count_24h",
        icon="mdi:alert-circle-outline",
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="errors",
        value_fn=lambda metrics: metrics.error_count_24h,
        extra_attrs_fn=lambda metrics: {
            "top_error_apps": metrics.top_error_apps,
            "top_error_hosts": metrics.top_error_hosts,
        },
    ),
    LogShedSensorEntityDescription(
        key="error_count_1h",
        translation_key="error_count_1h",
        icon="mdi:alert-circle",
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="errors",
        value_fn=lambda metrics: metrics.error_count_1h,
        extra_attrs_fn=lambda metrics: {
            "top_error_apps": metrics.top_error_apps,
            "top_error_hosts": metrics.top_error_hosts,
        },
    ),
    LogShedSensorEntityDescription(
        key="total_logs",
        translation_key="total_logs",
        icon="mdi:database",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="logs",
        value_fn=lambda metrics: metrics.total_logs_count,
    ),
    LogShedSensorEntityDescription(
        key="database_size",
        translation_key="database_size",
        icon="mdi:database-outline",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        value_fn=lambda metrics: metrics.db_size_mb,
    ),
    LogShedSensorEntityDescription(
        key="disk_free",
        translation_key="disk_free",
        icon="mdi:harddisk",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        value_fn=lambda metrics: round(metrics.disk_free_bytes / (1024**3), 2),
    ),
    LogShedSensorEntityDescription(
        key="disk_used_percent",
        translation_key="disk_used_percent",
        icon="mdi:chart-pie",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda metrics: metrics.disk_used_percent,
    ),
    LogShedSensorEntityDescription(
        key="queue_depth",
        translation_key="queue_depth",
        icon="mdi:tray-full",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="messages",
        value_fn=lambda metrics: metrics.queue_depth,
    ),
    LogShedSensorEntityDescription(
        key="dropped_logs",
        translation_key="dropped_logs",
        icon="mdi:delete-empty",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="logs",
        value_fn=lambda metrics: metrics.dropped_logs,
    ),
    LogShedSensorEntityDescription(
        key="filtered_logs",
        translation_key="filtered_logs",
        icon="mdi:filter-outline",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="logs",
        value_fn=lambda metrics: metrics.dropped_by_filter,
    ),
    LogShedSensorEntityDescription(
        key="maintenance_remaining",
        translation_key="maintenance_remaining",
        icon="mdi:clock-end",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        value_fn=lambda metrics: metrics.maintenance_remaining_seconds,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up LogShed sensor entities based on a config entry."""
    coordinator: LogShedDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        LogShedSensorEntity(coordinator, description) for description in SENSOR_DESCRIPTIONS
    )


class LogShedSensorEntity(LogShedEntity, SensorEntity):
    """Representation of a LogShed sensor."""

    entity_description: LogShedSensorEntityDescription

    def __init__(
        self,
        coordinator: LogShedDataUpdateCoordinator,
        description: LogShedSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        if not self.coordinator.data or not self.entity_description.extra_attrs_fn:
            return None
        return self.entity_description.extra_attrs_fn(self.coordinator.data)
