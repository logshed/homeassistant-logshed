"""Sensor platform for the LogShed integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfInformation, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import LogShedMetrics
from .coordinator import (
    SERVER_RECOVERY,
    SERVER_STATUSES,
    SERVER_UPGRADING,
    LogShedConfigEntry,
    LogShedDataUpdateCoordinator,
)
from .entity import LogShedEntity


@dataclass(frozen=True, kw_only=True)
class LogShedSensorEntityDescription(SensorEntityDescription):
    """Describes LogShed sensor entity."""

    value_fn: Callable[[LogShedMetrics], Any]
    extra_attrs_fn: Callable[[LogShedMetrics], dict[str, Any]] | None = None
    # Created only once LogShed reports the data (older servers do not)
    exists_fn: Callable[[LogShedMetrics], bool] | None = None


def _parse_time(value: Any) -> datetime | None:
    """An ISO 8601 time from LogShed as an aware datetime, or None."""
    return dt_util.parse_datetime(value) if isinstance(value, str) else None


def _sources_by_silence(metrics: LogShedMetrics) -> list[dict[str, Any]]:
    """The sources, the longest silent first; those not seen since LogShed 1.4.0 last."""
    sources = metrics.sources or []
    seen = [s for s in sources if _parse_time(s["last_seen"]) is not None]
    seen.sort(key=lambda s: _parse_time(s["last_seen"]))
    return seen + [s for s in sources if _parse_time(s["last_seen"]) is None]


def _longest_silent(metrics: LogShedMetrics) -> dict[str, Any] | None:
    ordered = _sources_by_silence(metrics)
    if ordered and _parse_time(ordered[0]["last_seen"]) is not None:
        return ordered[0]
    return None


def _longest_silent_attrs(metrics: LogShedMetrics) -> dict[str, Any]:
    quietest = _longest_silent(metrics)
    return {
        "source_name": quietest["name"] if quietest else None,
        "source_count": len(metrics.sources or []),
        "sources": _sources_by_silence(metrics),
    }


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
        key="error_or_worse_logs_24h",
        translation_key="error_or_worse_logs_24h",
        icon="mdi:alert-circle-outline",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="logs",
        value_fn=lambda metrics: metrics.error_count_24h,
        extra_attrs_fn=lambda metrics: {
            "top_error_apps": metrics.top_error_apps,
            "top_error_hosts": metrics.top_error_hosts,
        },
    ),
    LogShedSensorEntityDescription(
        key="error_or_worse_logs_1h",
        translation_key="error_or_worse_logs_1h",
        icon="mdi:alert-circle",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="logs",
        value_fn=lambda metrics: metrics.error_count_1h,
        extra_attrs_fn=lambda metrics: {
            "top_error_apps": metrics.top_error_apps,
            "top_error_hosts": metrics.top_error_hosts,
        },
    ),
    LogShedSensorEntityDescription(
        key="emergency_logs_24h",
        translation_key="emergency_logs_24h",
        icon="mdi:alarm-light",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="logs",
        value_fn=lambda metrics: metrics.emergency_logs_24h,
    ),
    LogShedSensorEntityDescription(
        key="alert_logs_24h",
        translation_key="alert_logs_24h",
        icon="mdi:bell-alert",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="logs",
        value_fn=lambda metrics: metrics.alert_logs_24h,
    ),
    LogShedSensorEntityDescription(
        key="critical_logs_24h",
        translation_key="critical_logs_24h",
        icon="mdi:alert-octagon",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="logs",
        value_fn=lambda metrics: metrics.critical_logs_24h,
    ),
    LogShedSensorEntityDescription(
        key="error_logs_24h",
        translation_key="error_logs_24h",
        icon="mdi:close-circle-outline",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="logs",
        value_fn=lambda metrics: metrics.error_logs_24h,
    ),
    LogShedSensorEntityDescription(
        key="warning_logs_24h",
        translation_key="warning_logs_24h",
        icon="mdi:alert-outline",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="logs",
        value_fn=lambda metrics: metrics.warning_logs_24h,
    ),
    LogShedSensorEntityDescription(
        key="total_logs",
        translation_key="total_logs",
        icon="mdi:database",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="logs",
        value_fn=lambda metrics: metrics.total_logs_count,
    ),
    LogShedSensorEntityDescription(
        key="database_size",
        entity_category=EntityCategory.DIAGNOSTIC,
        translation_key="database_size",
        icon="mdi:database-outline",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.MEGABYTES,
        suggested_display_precision=1,
        value_fn=lambda metrics: metrics.db_size_bytes,
    ),
    LogShedSensorEntityDescription(
        key="disk_free",
        entity_category=EntityCategory.DIAGNOSTIC,
        translation_key="disk_free",
        icon="mdi:harddisk",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        value_fn=lambda metrics: metrics.disk_free_bytes,
    ),
    LogShedSensorEntityDescription(
        key="disk_used_percent",
        entity_category=EntityCategory.DIAGNOSTIC,
        translation_key="disk_used_percent",
        icon="mdi:chart-pie",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda metrics: metrics.disk_used_percent,
    ),
    LogShedSensorEntityDescription(
        key="queue_depth",
        entity_category=EntityCategory.DIAGNOSTIC,
        translation_key="queue_depth",
        icon="mdi:tray-full",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="messages",
        value_fn=lambda metrics: metrics.queue_depth,
    ),
    LogShedSensorEntityDescription(
        key="dropped_logs",
        entity_category=EntityCategory.DIAGNOSTIC,
        translation_key="dropped_logs",
        icon="mdi:delete-empty",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="logs",
        value_fn=lambda metrics: metrics.dropped_logs,
    ),
    LogShedSensorEntityDescription(
        key="filtered_logs",
        entity_category=EntityCategory.DIAGNOSTIC,
        translation_key="filtered_logs",
        icon="mdi:filter-outline",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="logs",
        value_fn=lambda metrics: metrics.dropped_by_filter,
    ),
    LogShedSensorEntityDescription(
        key="udp_lost",
        entity_category=EntityCategory.DIAGNOSTIC,
        translation_key="udp_lost",
        icon="mdi:lan-disconnect",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="datagrams",
        value_fn=lambda metrics: metrics.udp_receive_errors,
    ),
    LogShedSensorEntityDescription(
        key="maintenance_remaining",
        translation_key="maintenance_remaining",
        icon="mdi:clock-end",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        value_fn=lambda metrics: metrics.maintenance_remaining_seconds,
    ),
    LogShedSensorEntityDescription(
        key="longest_silent_source",
        translation_key="longest_silent_source",
        icon="mdi:timer-sand",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda metrics: (
            _parse_time(quietest["last_seen"]) if (quietest := _longest_silent(metrics)) else None
        ),
        extra_attrs_fn=_longest_silent_attrs,
        exists_fn=lambda metrics: metrics.sources is not None,
    ),
    LogShedSensorEntityDescription(
        key="last_backup",
        entity_category=EntityCategory.DIAGNOSTIC,
        translation_key="last_backup",
        icon="mdi:database-export",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda metrics: (
            _parse_time(metrics.last_backup["created_at"]) if metrics.last_backup else None
        ),
        extra_attrs_fn=lambda metrics: {
            "size_bytes": metrics.last_backup["size_bytes"] if metrics.last_backup else None,
        },
        exists_fn=lambda metrics: metrics.reports_last_backup,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LogShedConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up LogShed sensor entities based on a config entry."""
    coordinator = entry.runtime_data.coordinator
    added: set[str] = set()

    @callback
    def _add_reported_sensors() -> None:
        """Add each sensor whose data LogShed reports, also after LogShed is upgraded."""
        if not coordinator.data:
            return
        new = [
            LogShedSensorEntity(coordinator, description)
            for description in SENSOR_DESCRIPTIONS
            if description.key not in added
            and (description.exists_fn is None or description.exists_fn(coordinator.data))
        ]
        added.update(entity.entity_description.key for entity in new)
        if new:
            async_add_entities(new)

    async_add_entities([LogShedServerStatusSensor(coordinator)])
    _add_reported_sensors()
    entry.async_on_unload(coordinator.async_add_listener(_add_reported_sensors))


class LogShedSensorEntity(LogShedEntity, SensorEntity):
    """Representation of a LogShed sensor."""

    entity_description: LogShedSensorEntityDescription
    # Longest Silent Source's list of every source changes on most polls; keep it out of the recorder
    _unrecorded_attributes = frozenset({"sources"})

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


class LogShedServerStatusSensor(LogShedEntity, SensorEntity):
    """Whether LogShed is running, upgrading its database, in recovery, failing or unreachable."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_options = SERVER_STATUSES
    _attr_translation_key = "server_status"
    _attr_icon = "mdi:server"

    def __init__(self, coordinator: LogShedDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "server_status")

    @property
    def available(self) -> bool:
        """Stay available when polling fails: that is what this sensor reports."""
        return True

    @property
    def native_value(self) -> str:
        """Return the server status."""
        return self.coordinator.server_status

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the upgrade stage and progress while upgrading or in recovery."""
        upgrade = self.coordinator.upgrade
        if self.coordinator.server_status not in (SERVER_UPGRADING, SERVER_RECOVERY):
            return None
        upgrade = upgrade or {}
        return {
            "stage": upgrade.get("stage"),
            "done": upgrade.get("done"),
            "total": upgrade.get("total"),
            "from_schema": upgrade.get("from_schema"),
            "target_schema": upgrade.get("target_schema"),
            "failed_at": upgrade.get("failed_at"),
        }
