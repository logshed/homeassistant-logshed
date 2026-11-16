"""Tests for LogShed sensor platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.logshed.api import (
    LogShedApiClient,
    LogShedCannotConnect,
    LogShedHealth,
    LogShedMetrics,
)

from .conftest import (
    MOCK_HEALTH_UPGRADING_RESPONSE,
    MOCK_SYSTEM_METRICS_140_RESPONSE,
    setup_integration,
)


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
        assert state.attributes.get("state_class") == "measurement"

    # 4. Total Logs
    state = hass.states.get("sensor.logshed_total_logs")
    assert state is not None
    assert int(state.state) == 500000
    assert state.attributes.get("state_class") == "measurement"

    # 5. Database Size
    state = hass.states.get("sensor.logshed_database_size")
    assert state is not None
    # 104857600 bytes shown in decimal megabytes
    assert float(state.state) == pytest.approx(104.8576)
    assert state.attributes.get("unit_of_measurement") == "MB"
    assert state.attributes.get("device_class") == "data_size"

    # 6. Disk Free
    state = hass.states.get("sensor.logshed_disk_free")
    assert state is not None
    # 107374182400 bytes (100 GiB) shown in decimal gigabytes
    assert float(state.state) == pytest.approx(107.3741824)
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

    # 10a. UDP Lost
    state = hass.states.get("sensor.logshed_udp_lost")
    assert state is not None
    assert int(state.state) == 7
    assert state.attributes.get("unit_of_measurement") == "datagrams"
    assert state.attributes.get("state_class") == "total_increasing"

    # 11. Maintenance Remaining
    state = hass.states.get("sensor.logshed_maintenance_remaining")
    assert state is not None
    # 1800 seconds shown in minutes with no decimals
    assert float(state.state) == pytest.approx(30)
    assert state.attributes.get("unit_of_measurement") == "min"

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
        "udp_lost",
        "server_status",
    }
    # 17 from the metrics and Server Status; LogShed 1.3.x reports no sources or backups
    sensor_entries = er.async_entries_for_config_entry(entity_reg, mock_config_entry.entry_id)
    assert len(sensor_entries) == 18
    for reg_entry in sensor_entries:
        key = reg_entry.unique_id.removeprefix(f"{mock_metrics.instance_id}_")
        expected = EntityCategory.DIAGNOSTIC if key in diagnostic else None
        assert reg_entry.entity_category == expected, key


async def test_error_or_worse_sensors_are_measurements(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test the rolling error or worse counts are gauges, not totals."""
    await setup_integration(hass, mock_config_entry, mock_api_client, [Platform.SENSOR])

    for entity_id in (
        "sensor.logshed_error_or_worse_logs_24h",
        "sensor.logshed_error_or_worse_logs_1h",
    ):
        assert hass.states.get(entity_id).attributes.get("state_class") == "measurement"


async def test_udp_lost_unknown_when_not_reported(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
    mock_metrics: LogShedMetrics,
) -> None:
    """Test UDP Lost is unknown when LogShed cannot read the counter (null)."""
    mock_metrics.udp_receive_errors = None
    await setup_integration(hass, mock_config_entry, mock_api_client, [Platform.SENSOR])

    assert hass.states.get("sensor.logshed_udp_lost").state == "unknown"


async def test_new_sensors_need_the_server_data(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """LogShed 1.3.x reports no sources or backups: those sensors are not created."""
    await setup_integration(hass, mock_config_entry, mock_api_client, [Platform.SENSOR])

    assert hass.states.get("sensor.logshed_longest_silent_source") is None
    assert hass.states.get("sensor.logshed_last_backup") is None
    assert hass.states.get("sensor.logshed_server_status").state == "running"


async def test_longest_silent_source_and_last_backup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """The longest-silent source's last log is the state; never-seen sources are listed last."""
    mock_api_client.async_get_system_metrics = AsyncMock(
        return_value=LogShedMetrics.from_dict(MOCK_SYSTEM_METRICS_140_RESPONSE)
    )
    await setup_integration(hass, mock_config_entry, mock_api_client, [Platform.SENSOR])
    entity_reg = er.async_get(hass)

    state = hass.states.get("sensor.logshed_longest_silent_source")
    assert state.state == "2026-11-16T07:30:00+00:00"
    assert state.attributes["device_class"] == "timestamp"
    assert state.attributes["source_name"] == "Media server"
    assert state.attributes["source_count"] == 3
    assert [s["name"] for s in state.attributes["sources"]] == ["Media server", "nas", "printer"]
    # The list changes on most polls, so it stays out of the recorder
    assert "sources" in state.state_info["unrecorded_attributes"]
    entry = entity_reg.async_get("sensor.logshed_longest_silent_source")
    assert entry.entity_category is None

    state = hass.states.get("sensor.logshed_last_backup")
    assert state.state == "2026-11-10T08:00:00+00:00"
    assert state.attributes["size_bytes"] == 1234567
    entry = entity_reg.async_get("sensor.logshed_last_backup")
    assert entry.entity_category == EntityCategory.DIAGNOSTIC


async def test_new_sensors_unknown_without_data(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """No source seen since 1.4.0 and no backup yet: both sensors exist, unknown."""
    data = {
        **MOCK_SYSTEM_METRICS_140_RESPONSE,
        "sources": [{"name": "nas", "kind": "syslog", "address": "10.0.0.5", "last_seen": None}],
        "last_backup": None,
    }
    mock_api_client.async_get_system_metrics = AsyncMock(
        return_value=LogShedMetrics.from_dict(data)
    )
    await setup_integration(hass, mock_config_entry, mock_api_client, [Platform.SENSOR])

    state = hass.states.get("sensor.logshed_longest_silent_source")
    assert state.state == "unknown"
    assert state.attributes["source_name"] is None
    assert state.attributes["source_count"] == 1
    state = hass.states.get("sensor.logshed_last_backup")
    assert state.state == "unknown"
    assert state.attributes["size_bytes"] is None


async def test_new_sensors_appear_when_logshed_is_upgraded(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Upgrading LogShed from 1.3.x adds the sensors on the next poll, without a reload."""
    await setup_integration(hass, mock_config_entry, mock_api_client, [Platform.SENSOR])
    assert hass.states.get("sensor.logshed_last_backup") is None

    mock_api_client.async_get_system_metrics = AsyncMock(
        return_value=LogShedMetrics.from_dict(MOCK_SYSTEM_METRICS_140_RESPONSE)
    )
    await mock_config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get("sensor.logshed_last_backup").state == "2026-11-10T08:00:00+00:00"
    assert hass.states.get("sensor.logshed_longest_silent_source") is not None

    # A later poll adds nothing twice
    await mock_config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    entries = er.async_entries_for_config_entry(er.async_get(hass), mock_config_entry.entry_id)
    assert len(entries) == len(hass.states.async_all("sensor")) == 20


async def test_server_status_while_upgrading(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """While LogShed upgrades, Server Status says so with the progress; figures are unavailable."""
    await setup_integration(hass, mock_config_entry, mock_api_client, [Platform.SENSOR])
    entity_reg = er.async_get(hass)
    entry = entity_reg.async_get("sensor.logshed_server_status")
    assert entry.entity_category == EntityCategory.DIAGNOSTIC
    assert hass.states.get("sensor.logshed_server_status").attributes["options"] == [
        "running",
        "upgrading",
        "recovery",
        "error",
        "unreachable",
    ]

    mock_api_client.async_get_system_metrics = AsyncMock(
        side_effect=LogShedCannotConnect("LogShed is upgrading its database.", status=503)
    )
    mock_api_client.async_get_health = AsyncMock(
        return_value=LogShedHealth.from_dict(MOCK_HEALTH_UPGRADING_RESPONSE)
    )
    await mock_config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get("sensor.logshed_server_status")
    assert state.state == "upgrading"
    assert state.attributes["stage"] == "migrate"
    assert (state.attributes["done"], state.attributes["total"]) == (2, 5)
    assert hass.states.get("sensor.logshed_ingestion_rate").state == "unavailable"

    # LogShed down: unreachable, still available, no progress
    mock_api_client.async_get_system_metrics = AsyncMock(
        side_effect=LogShedCannotConnect("Timeout connecting to LogShed")
    )
    await mock_config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get("sensor.logshed_server_status")
    assert state.state == "unreachable"
    assert "stage" not in state.attributes
