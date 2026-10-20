# LogShed Home Assistant Integration

[![Validate](https://github.com/logshed/homeassistant-logshed/actions/workflows/validate.yml/badge.svg)](https://github.com/logshed/homeassistant-logshed/actions/workflows/validate.yml)
[![Test](https://github.com/logshed/homeassistant-logshed/actions/workflows/test.yml/badge.svg)](https://github.com/logshed/homeassistant-logshed/actions/workflows/test.yml)
[![HACS Default](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/default)
[![Version](https://img.shields.io/github/v/release/logshed/homeassistant-logshed)](https://github.com/logshed/homeassistant-logshed/releases)

> [!IMPORTANT]
> **Pre-release Notice:** This integration is currently in pre-release and requires LogShed server version **1.3.0** or later. It relies on the external REST metrics and maintenance API endpoints introduced in LogShed 1.3.0 and will not work with older LogShed versions.

The official [Home Assistant Community Store (HACS)](https://hacs.xyz/) custom integration for **LogShed** (requires LogShed server v1.3.0+).

Connects your Home Assistant instance with your self-hosted [LogShed](https://github.com/logshed/logshed) server to deliver real-time ingestion telemetry, error tracking with top offending services, storage stats, automated maintenance window controls, diagnostic buttons, and smart home alert triggers.

---

## Features

- **Real-time & Historical Telemetry:** Native Long-Term Statistics (LTS) for ingestion throughput (`logs/s`), rolling error statistics (1h, 24h, and 24h per severity from emergency to warning), storage metrics, and log counts.
- **Incident & Problem Sensors:** Binary problem sensors reflecting LogShed alert rules (ideal for flashing desk lamps red or sending high-priority alerts).
- **Automated Maintenance Integration:** Native switches and service actions (`logshed.enable_maintenance`, `logshed.disable_maintenance`) for backup hooks (Home Assistant Backups, Proxmox VE backups, restic, Borg) to silence alerts or drop error floods during scheduled backup routines.
- **Diagnostic Controls:** On-demand database compaction (`VACUUM`) and retention pruning buttons directly within Home Assistant.

---

## Installation

### Method 1: HACS (Recommended)

1. Ensure [HACS](https://hacs.xyz/) is installed in your Home Assistant instance.
2. In Home Assistant, navigate to **HACS > Integrations**.
3. Click the top-right menu icon (three dots) and select **Custom repositories**.
4. Enter `https://github.com/logshed/homeassistant-logshed` as the repository URL, select **Integration** as the category, and click **Add**.
5. Find **LogShed** in the integration list and click **Download**.
6. Restart Home Assistant.

### Method 2: Manual Installation

1. Download the latest release from the [Releases](https://github.com/logshed/homeassistant-logshed/releases) page.
2. Copy the `custom_components/logshed/` folder into your Home Assistant `<config>/custom_components/` directory.
3. Restart Home Assistant.

---

## Configuration

1. In Home Assistant, go to **Settings > Devices & Services**.
2. Click **Add Integration** and search for **LogShed**.
3. Enter your LogShed connection details:
   - **Host URL:** The base URL of your LogShed server (e.g. `http://192.168.1.100:8000`).
   - **API Token:** A LogShed API Bearer token starting with `ls_live_...`.
     - *Recommended:* Generate a token in LogShed under **Settings > API & MCP Access** with Full Access (`*`) or `system:read`, `system:write`, and `maintenance:write` scopes.
   - **Verify SSL Certificate:** Uncheck if using a self-signed HTTPS certificate in your home lab.
   - **Default Maintenance Duration (minutes):** Duration in minutes (5 to 720, default: 60) used when toggling maintenance mode on.
4. Click **Submit**. All entities will be automatically created under a single LogShed device.

### Options

Click **Configure** on the LogShed integration card to adjust runtime options:
- **Metrics Polling Interval:** 10 to 300 seconds (default: 30s).
- **Default Maintenance Duration:** 5 to 720 minutes (default: 60m).
- **Default Maintenance Log Handling:** Silence alerts only (`silence_alerts`) or silence alerts and drop incoming errors (`drop_errors`).

---

## Entities

### Sensors

| Entity ID | Name | Unit | Class | Description |
| :--- | :--- | :--- | :--- | :--- |
| `sensor.logshed_ingestion_rate` | Ingestion Rate | `logs/s` | `measurement` | Real-time log ingestion rate. |
| `sensor.logshed_error_or_worse_logs_24h` | Error or Worse Logs 24h | `logs` | `total` | Rolling 24-hour count of emergency, alert, critical and error (severity 0 to 3) logs combined. Includes `top_error_apps` and `top_error_hosts` attributes. |
| `sensor.logshed_error_or_worse_logs_1h` | Error or Worse Logs 1h | `logs` | `total` | Rolling 1-hour count of severity 0 to 3 logs combined. Includes `top_error_apps` and `top_error_hosts` attributes. |
| `sensor.logshed_emergency_logs_24h` | Emergency Logs 24h | `logs` | `total` | Rolling 24-hour count of emergency (severity 0) logs. |
| `sensor.logshed_alert_logs_24h` | Alert Logs 24h | `logs` | `total` | Rolling 24-hour count of alert (severity 1) logs. Not related to LogShed alert rules. |
| `sensor.logshed_critical_logs_24h` | Critical Logs 24h | `logs` | `total` | Rolling 24-hour count of critical (severity 2) logs. |
| `sensor.logshed_error_logs_24h` | Error Logs 24h | `logs` | `total` | Rolling 24-hour count of error (severity 3) logs only. |
| `sensor.logshed_warning_logs_24h` | Warning Logs 24h | `logs` | `total` | Rolling 24-hour count of warning (severity 4) logs. |
| `sensor.logshed_total_logs` | Total Logs | `logs` | `measurement` | Current count of stored logs in the database. |
| `sensor.logshed_maintenance_remaining`| Maintenance Remaining| `s` | `duration` | Seconds remaining in the current active maintenance window. |

### Diagnostic Sensors

Server health sensors are in the **Diagnostic** card on the device page, so the **Sensors** card keeps the log activity sensors together. They work in automations and keep long-term statistics like any other sensor, but the auto-generated default dashboard leaves them out.

| Entity ID | Name | Unit | Class | Description |
| :--- | :--- | :--- | :--- | :--- |
| `sensor.logshed_database_size` | Database Size | `MB` | `data_size` | SQLite database file size. |
| `sensor.logshed_disk_free` | Disk Space Free | `GB` | `data_size` | Free space on the LogShed storage mount. |
| `sensor.logshed_disk_used_percent` | Disk Used | `%` | `measurement` | Storage mount disk usage percentage. |
| `sensor.logshed_queue_depth` | Queue Depth | `messages` | `measurement` | Pending messages in the in-memory ring buffer. |
| `sensor.logshed_dropped_logs` | Dropped Logs | `logs` | `total_increasing` | Logs dropped due to ring buffer overflow. |
| `sensor.logshed_filtered_logs` | Filtered Logs | `logs` | `total_increasing` | Logs discarded by active drop rules or maintenance filters. |

### Binary Sensors

| Entity ID | Name | Device Class | Description |
| :--- | :--- | :--- | :--- |
| `binary_sensor.logshed_alert_state` | Alert Active | `problem` | **`on`** when any alert rule triggered in the sliding 15-minute window. Daily digests, on-demand AI analyses and maintenance windows do not turn it on. |
| `binary_sensor.logshed_maintenance_active` | Maintenance Active | None | **`on`** when any maintenance session is currently active. |
| `binary_sensor.logshed_connectivity` | Connectivity | `connectivity` | **`on`** when Home Assistant successfully communicates with LogShed. |

### Switches & Buttons

| Entity ID | Type | Description |
| :--- | :--- | :--- |
| `switch.logshed_maintenance_mode` | Switch | Toggles an on-demand maintenance window using default options. |
| `button.logshed_prune_database` | Button | Manually triggers database retention pruning and compaction. |
| `button.logshed_vacuum_database` | Button | Manually executes a database `VACUUM` to reclaim freelist disk pages. |

---

## Service Actions

### `logshed.enable_maintenance`

Starts an on-demand maintenance session to silence alert rules and optionally drop error logs.

```yaml
service: logshed.enable_maintenance
data:
  duration_minutes: 60
  reason: "Nightly backup routine"
  log_handling: "drop_errors"
  target_app: "postgres"
```

### `logshed.disable_maintenance`

Terminates active on-demand maintenance sessions immediately.

```yaml
service: logshed.disable_maintenance
data:
  session_id: ""  # Leave blank to clear all active sessions
```

---

## Lovelace Card Examples

### ApexCharts Card: Ingestion Throughput

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: LogShed Ingestion Throughput
  show_states: true
  colorize_states: true
graph_span: 12h
series:
  - entity: sensor.logshed_ingestion_rate
    name: Ingestion Rate
    type: line
    color: '#3b82f6'
    stroke_width: 2
    curve: smooth
    group_by:
      func: avg
      duration: 5m
```

### Native History Graph: Error Counts

```yaml
type: history-graph
title: LogShed System Health
hours_to_show: 24
entities:
  - entity: sensor.logshed_error_or_worse_logs_24h
    name: Rolling 24h Errors
  - entity: sensor.logshed_error_or_worse_logs_1h
    name: Recent 1h Errors
  - entity: sensor.logshed_queue_depth
    name: Buffer Queue Depth
```

---

## Automation Recipes

### Incident Warning Light

Pulse an office light red when a LogShed incident alert triggers:

```yaml
alias: "LogShed: Incident Warning Light"
description: "Turn desk lamp red when a LogShed alert triggers"
trigger:
  - platform: state
    entity_id: binary_sensor.logshed_alert_state
    to: "on"
action:
  - service: light.turn_on
    target:
      entity_id: light.office_desk_lamp
    data:
      rgb_color: [255, 0, 0]
      brightness: 255
  - service: notify.persistent_notification
    data:
      title: "LogShed Alert Firing"
      message: >-
        Rule '{{ state_attr('binary_sensor.logshed_alert_state', 'last_rule_name') }}'
        triggered at {{ state_attr('binary_sensor.logshed_alert_state', 'last_triggered_at') }}.
```

### Automated Backup Maintenance Window

Silence alerts and drop noisy errors while running scheduled backups:

```yaml
alias: "Home Lab: Nightly Backup Maintenance Window"
description: "Manage LogShed maintenance window during nightly backup job"
trigger:
  - platform: time
    at: "03:00:00"
action:
  - service: logshed.enable_maintenance
    data:
      duration_minutes: 60
      reason: "Nightly Proxmox and Home Assistant snapshot backup"
      log_handling: "drop_errors"
  - service: script.run_nightly_backups
  - service: logshed.disable_maintenance
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
