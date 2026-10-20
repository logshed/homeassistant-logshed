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
- **Update Notifications:** An update entity shows when a newer stable LogShed release is available.
- **Diagnostics:** Download config entry diagnostics (API token redacted) from the integration page for troubleshooting.

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

## Requirements

- Home Assistant **2024.12.0** or later.
- LogShed server **1.3.0** or later.

---

## Configuration

1. In Home Assistant, go to **Settings > Devices & Services**.
2. Click **Add Integration** and search for **LogShed**.
3. Enter your LogShed connection details:
   - **Host URL:** The base URL of your LogShed server (e.g. `http://192.168.1.100:8000`).
   - **API Token:** A LogShed API Bearer token starting with `ls_live_...`.
     - *Recommended:* Generate a token in LogShed under **Settings > API & MCP Access** with Full Access (`*`) or `system:read`, `system:write`, and `maintenance:write` scopes.
   - **Verify SSL Certificate:** Uncheck if using a self-signed HTTPS certificate in your home lab.
   - **Default Maintenance Duration (minutes):** Duration in minutes (5 to 720, default: 60) used when turning Quick Maintenance on.
4. Click **Submit**. All entities will be automatically created under a single device named after the LogShed server.

### Token Scopes

`system:read` is required. The other scopes add controls, and are checked each time the integration loads, so a token whose scopes change on the LogShed server is picked up after a reload:

| Scope | Adds |
| :--- | :--- |
| `system:read` | All sensors, binary sensors and the update entity (required). |
| `maintenance:write` | The Quick Maintenance switch and the `logshed.enable_maintenance` and `logshed.disable_maintenance` actions. Without it the switch is not created and the actions fail with a clear error. |
| `system:write` | The Prune Database and Vacuum Database buttons. Without it they are not created. |

### Entity IDs

The device takes the LogShed **server name** (Settings in LogShed, default `LogShed`), and entity IDs follow it. With the default name the IDs are `sensor.logshed_*`, as used throughout this README; a server named `Homelab Logs` gives `sensor.homelab_logs_*`.

### Changing the Address

If LogShed moves to a new address, open the LogShed integration card, choose **Reconfigure** and enter the new host URL (the API token stays the same). Adding the same LogShed instance again also updates the address of the existing entry. Reconfigure and reauthentication refuse a server that is a different LogShed instance.

### Options

Click **Configure** on the LogShed integration card to adjust runtime options:
- **Metrics Polling Interval:** 10 to 300 seconds (default: 30s).
- **Default Maintenance Duration:** 5 to 720 minutes (default: 60m).
- **Default Maintenance Log Handling:** Silence alerts only (`silence_alerts`) or silence alerts and drop incoming errors (`drop_errors`).

---

## Entities

### Sensors

The rolling counts are gauges (`measurement`) that rise and fall as logs age out of the window, so Home Assistant keeps their minimum, maximum and mean in long-term statistics.

| Entity ID | Name | Unit | Class | Description |
| :--- | :--- | :--- | :--- | :--- |
| `sensor.logshed_ingestion_rate` | Ingestion Rate | `logs/s` | `measurement` | Real-time log ingestion rate. |
| `sensor.logshed_error_or_worse_logs_24h` | Error or Worse Logs 24h | `logs` | `measurement` | Rolling 24-hour count of emergency, alert, critical and error (severity 0 to 3) logs combined. Includes `top_error_apps` and `top_error_hosts` attributes. |
| `sensor.logshed_error_or_worse_logs_1h` | Error or Worse Logs 1h | `logs` | `measurement` | Rolling 1-hour count of severity 0 to 3 logs combined. Includes `top_error_apps` and `top_error_hosts` attributes. |
| `sensor.logshed_emergency_logs_24h` | Emergency Logs 24h | `logs` | `measurement` | Rolling 24-hour count of emergency (severity 0) logs. |
| `sensor.logshed_alert_logs_24h` | Alert Logs 24h | `logs` | `measurement` | Rolling 24-hour count of alert (severity 1) logs. Not related to LogShed alert rules. |
| `sensor.logshed_critical_logs_24h` | Critical Logs 24h | `logs` | `measurement` | Rolling 24-hour count of critical (severity 2) logs. |
| `sensor.logshed_error_logs_24h` | Error Logs 24h | `logs` | `measurement` | Rolling 24-hour count of error (severity 3) logs only. |
| `sensor.logshed_warning_logs_24h` | Warning Logs 24h | `logs` | `measurement` | Rolling 24-hour count of warning (severity 4) logs. |
| `sensor.logshed_total_logs` | Total Logs | `logs` | `measurement` | Current count of stored logs in the database. |
| `sensor.logshed_maintenance_remaining`| Maintenance Remaining| `s` | `duration` | Seconds remaining in the current active maintenance window. |

### Diagnostic Sensors

Server health sensors are in the **Diagnostic** card on the device page, so the **Sensors** card keeps the log activity sensors together. They work in automations and keep long-term statistics like any other sensor, but the auto-generated default dashboard leaves them out.

| Entity ID | Name | Unit | Class | Description |
| :--- | :--- | :--- | :--- | :--- |
| `sensor.logshed_database_size` | Database Size | `MB` | `data_size` | SQLite database file size. Reported in bytes and shown in MB by default; change the unit in the entity settings. |
| `sensor.logshed_disk_free` | Disk Free | `GB` | `data_size` | Free space on the LogShed storage mount. Reported in bytes and shown in GB by default. |
| `sensor.logshed_disk_used_percent` | Disk Used Percent | `%` | `measurement` | Storage mount disk usage percentage. |
| `sensor.logshed_queue_depth` | Queue Depth | `messages` | `measurement` | Pending messages in the in-memory ring buffer. |
| `sensor.logshed_dropped_logs` | Dropped Logs | `logs` | `total_increasing` | Logs dropped due to ring buffer overflow. |
| `sensor.logshed_filtered_logs` | Filtered Logs | `logs` | `total_increasing` | Logs discarded by active drop rules or maintenance filters. |
| `sensor.logshed_udp_lost` | UDP Lost | `datagrams` | `total_increasing` | UDP syslog datagrams the kernel discarded because LogShed's receive buffer was full. Counts from when LogShed started and goes back to 0 when it restarts. With `network_mode: host` it covers every UDP socket on the host. Unknown when LogShed cannot read the counter (not Linux, or before the syslog listener starts). If it keeps rising, see [Sending Logs](https://github.com/logshed/logshed/blob/main/docs/SENDING_LOGS.md) on choosing UDP or TCP syslog. |

### Binary Sensors

| Entity ID | Name | Device Class | Description |
| :--- | :--- | :--- | :--- |
| `binary_sensor.logshed_alert_state` | Alert State | `problem` | **`on`** when any alert rule triggered in the sliding 15-minute window. Daily digests, on-demand AI analyses and maintenance windows do not turn it on. |
| `binary_sensor.logshed_maintenance_active` | Maintenance Active | None | **`on`** when any maintenance is active: on-demand sessions from any source (Home Assistant, the LogShed web UI, MCP clients) and scheduled windows. |
| `binary_sensor.logshed_connectivity` | Connectivity | `connectivity` | **`on`** when Home Assistant reaches LogShed, **`off`** when polling fails (it never becomes unavailable). Diagnostic entity. |

### Switches & Buttons

| Entity ID | Type | Description |
| :--- | :--- | :--- |
| `switch.logshed_quick_maintenance` | Switch | Quick Maintenance: starts a maintenance window with the default duration and log handling from the integration options. It is **`on`** only while that window runs; turning it off ends only that window. Windows started by `logshed.enable_maintenance`, the LogShed web UI, MCP clients or a schedule never turn it on and are never ended by it (`binary_sensor.logshed_maintenance_active` shows those). It turns off by itself when its window ends, and remembers its window across Home Assistant restarts. Needs `maintenance:write`. |
| `button.logshed_prune_database` | Button | Manually triggers database retention pruning and compaction. Needs `system:write`. |
| `button.logshed_vacuum_database` | Button | Manually executes a database `VACUUM` to reclaim freelist disk pages. Needs `system:write`. |

Prune and vacuum run inside the request on the LogShed server, and a vacuum of a large database can take minutes. Home Assistant waits up to 10 minutes; if LogShed has not answered by then, the error says the operation may still be running on the server.

### Update

| Entity ID | Description |
| :--- | :--- |
| `update.logshed_update` | Shows the installed LogShed version and the latest stable release, with a link to its release notes. **`on`** when a newer stable release is available, using LogShed's own version comparison (a pre-release install is not reported as outdated by an older stable release). Checked once an hour, matching LogShed's cached update check. Unknown when update checks are turned off in LogShed or the last check could not reach the registry. It only reports updates: update LogShed by pulling the new container image. Diagnostic entity; LogShed servers without the version endpoint get no update entity. |

---

## Service Actions

Both actions take an optional `config_entry_id` (the **LogShed Instance** picker) to target one LogShed instance. Without it they apply to every loaded instance. They need the `maintenance:write` scope.

### `logshed.enable_maintenance`

Starts an on-demand maintenance session to silence alert rules and optionally drop error logs. It returns the session it started on each instance, so an automation can later end exactly that session:

```yaml
action: logshed.enable_maintenance
data:
  duration_minutes: 60
  reason: "Nightly backup routine"
  log_handling: "drop_errors"
  target_app: "postgres"
response_variable: maintenance
```

Response:

```yaml
sessions:
  - config_entry_id: 01JABC...
    session_id: 3f2b9c1e-...
    until: "2026-10-20T04:00:00+00:00"
```

### `logshed.disable_maintenance`

Ends maintenance sessions. Pass a `session_id` returned by `logshed.enable_maintenance` to end only that session.

> [!WARNING]
> Without a `session_id`, every active on-demand session on the targeted instances is ended, including sessions started from the LogShed web UI, MCP clients or other automations. Scheduled windows are never ended.

```yaml
action: logshed.disable_maintenance
data:
  session_id: "{{ maintenance.sessions[0].session_id }}"
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
  - action: light.turn_on
    target:
      entity_id: light.office_desk_lamp
    data:
      rgb_color: [255, 0, 0]
      brightness: 255
  - action: notify.persistent_notification
    data:
      title: "LogShed Alert Firing"
      message: >-
        Rule '{{ state_attr('binary_sensor.logshed_alert_state', 'last_rule_name') }}'
        triggered at {{ state_attr('binary_sensor.logshed_alert_state', 'last_triggered_at') }}.
```

### Automated Backup Maintenance Window

Silence alerts and drop noisy errors while running scheduled backups. The automation ends only the session it started, so maintenance started by someone else keeps running. If the backup script fails, the session still ends on its own after `duration_minutes`.

```yaml
alias: "Home Lab: Nightly Backup Maintenance Window"
description: "Manage LogShed maintenance window during nightly backup job"
trigger:
  - platform: time
    at: "03:00:00"
action:
  - action: logshed.enable_maintenance
    data:
      duration_minutes: 60
      reason: "Nightly Proxmox and Home Assistant snapshot backup"
      log_handling: "drop_errors"
    response_variable: maintenance
  - action: script.run_nightly_backups
  - repeat:
      for_each: "{{ maintenance.sessions }}"
      sequence:
        - action: logshed.disable_maintenance
          data:
            config_entry_id: "{{ repeat.item.config_entry_id }}"
            session_id: "{{ repeat.item.session_id }}"
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
