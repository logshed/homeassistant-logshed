"""Tests for LogShed sensor platform."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.logshed.api import LogShedApiClient, LogShedMetrics


async def test_sensors_state_and_attributes(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
    mock_metrics: LogShedMetrics,
) -> None:
    """Test all LogShed sensors register with correct states and attributes."""
    mock_config_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.logshed.LogShedApiClient",
            return_value=mock_api_client,
        ),
        patch("custom_components.logshed.PLATFORMS", [Platform.SENSOR]),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    entity_reg = er.async_get(hass)

    # 1. Ingestion Rate
    state = hass.states.get("sensor.logshed_ingestion_rate")
    assert state is not None
    assert float(state.state) == 42.5
    assert state.attributes.get("unit_of_measurement") == "logs/s"

    # 2. Errors 24h & breakdown attributes
    state = hass.states.get("sensor.logshed_error_or_worse_logs_24h")
    assert state is not None
    assert int(state.state) == 17
    assert state.attributes.get("unit_of_measurement") == "logs"
    assert state.attributes.get("top_error_apps") == [
        {"name": "postgres", "count": 12},
        {"name": "traefik", "count": 5},
    ]
    assert state.attributes.get("top_error_hosts") == [
        {"name": "compute-01", "count": 14},
        {"name": "nas", "count": 3},
    ]

    # 3. Errors 1h
    state = hass.states.get("sensor.logshed_error_or_worse_logs_1h")
    assert state is not None
    assert int(state.state) == 3
    assert state.attributes.get("top_error_apps") == [
        {"name": "postgres", "count": 12},
        {"name": "traefik", "count": 5},
    ]

    # 3a. Per-severity 24h counts (emergency to warning)
    for entity_id, expected in (
        ("sensor.logshed_emergency_logs_24h", 0),
        ("sensor.logshed_alert_logs_24h", 1),
        ("sensor.logshed_critical_logs_24h", 4),
        ("sensor.logshed_error_logs_24h", 12),
        ("sensor.logshed_warning_logs_24h", 23),
    ):
        state = hass.states.get(entity_id)
        assert state is not None, entity_id
        assert int(state.state) == expected
        assert state.attributes.get("unit_of_measurement") == "logs"
        assert state.attributes.get("state_class") == "total"

    # 4. Total Logs
    state = hass.states.get("sensor.logshed_total_logs")
    assert state is not None
    assert int(state.state) == 500000
    assert state.attributes.get("state_class") == "measurement"

    # 5. Database Size
    state = hass.states.get("sensor.logshed_database_size")
    assert state is not None
    assert float(state.state) == 100.0
    assert state.attributes.get("unit_of_measurement") == "MB"

    # 6. Disk Free
    state = hass.states.get("sensor.logshed_disk_free")
    assert state is not None
    assert float(state.state) == 100.0
    assert state.attributes.get("unit_of_measurement") == "GB"

    # 7. Disk Used Percent
    state = hass.states.get("sensor.logshed_disk_used_percent")
    assert state is not None
    assert float(state.state) == 50.0
    assert state.attributes.get("unit_of_measurement") == "%"
    assert state.attributes.get("icon") == "mdi:chart-pie"

    # 8. Queue Depth
    state = hass.states.get("sensor.logshed_queue_depth")
    assert state is not None
    assert int(state.state) == 5

    # 9. Dropped Logs
    state = hass.states.get("sensor.logshed_dropped_logs")
    assert state is not None
    assert int(state.state) == 10

    # 10. Filtered Logs
    state = hass.states.get("sensor.logshed_filtered_logs")
    assert state is not None
    assert int(state.state) == 25

    # 11. Maintenance Remaining
    state = hass.states.get("sensor.logshed_maintenance_remaining")
    assert state is not None
    assert int(state.state) == 1800
    assert state.attributes.get("unit_of_measurement") == "s"

    # Check unique ID format on an entity
    entry = entity_reg.async_get("sensor.logshed_ingestion_rate")
    assert entry is not None
    assert entry.unique_id == f"{mock_metrics.instance_id}_ingestion_rate"

    # Server health sensors sit in the Diagnostic card; log activity sensors stay in Sensors
    diagnostic = {
        "database_size",
        "disk_free",
        "disk_used_percent",
        "queue_depth",
        "dropped_logs",
        "filtered_logs",
    }
    sensor_entries = er.async_entries_for_config_entry(entity_reg, mock_config_entry.entry_id)
    assert len(sensor_entries) == 16
    for reg_entry in sensor_entries:
        key = reg_entry.unique_id.removeprefix(f"{mock_metrics.instance_id}_")
        expected = EntityCategory.DIAGNOSTIC if key in diagnostic else None
        assert reg_entry.entity_category == expected, key
