# Changelog

All notable changes to the LogShed Home Assistant integration will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-16

### Added
- Initial release of the official LogShed Home Assistant custom integration.
- Dedicated UI config flow with Bearer token authentication (`ls_live_...`), token scope verification, and SSL verification options.
- Dynamic options flow to configure metrics polling interval (10 to 300s), default maintenance duration (5 to 720 min), and default maintenance log handling mode (`silence_alerts` or `drop_errors`).
- Reauthentication flow handling expired or rotated API tokens with automatic reload.
- `LogShedDataUpdateCoordinator` polling `/api/v1/system/metrics` with automatic error propagation and offline state handling.
- 16 sensor entities for real-time and Long-Term Statistics (LTS):
  - Ingestion Rate (`logs/s`)
  - Rolling 24-hour and 1-hour Error or Worse Logs (severities 0 to 3 combined) with top offending applications (`top_error_apps`) and hosts (`top_error_hosts`)
  - Rolling 24-hour log counts per severity: Emergency, Alert, Critical, Error and Warning
  - Total Stored Logs
  - Database File Size (`MB`)
  - Free Disk Space (`GB`)
  - Disk Used Percent (`%`)
  - In-memory Queue Depth
  - Dropped Logs & Filtered Logs
  - Maintenance Remaining (`s`)
- Server health sensors (Database Size, Free Disk Space, Disk Used Percent, Queue Depth, Dropped Logs and Filtered Logs) are diagnostic entities, so the device page keeps the log activity sensors together.
- 3 binary sensors:
  - Alert State (sliding 15-minute problem state class)
  - Maintenance Active (with session attributes: `until`, `remaining_seconds`, `active_sessions_count`, `log_handling`)
  - Connectivity status
- `switch.logshed_maintenance_mode` to toggle on-demand maintenance windows with customizable default duration.
- Diagnostic buttons for manual maintenance:
  - Prune Database (with 409 conflict, 429 rate limit cooldown, and 400 disk space error handling)
  - Vacuum Database
- Home Assistant service actions:
  - `logshed.enable_maintenance`: Start targeted maintenance windows with custom duration, reason, target app/host filters, and log handling modes.
  - `logshed.disable_maintenance`: Terminate specific or all active maintenance windows.
- Local brand proxy assets (`brand/icon.png`, `brand/logo.png`) complying with Home Assistant 2026.3+ specifications.
- Full English translations (`strings.json`, `translations/en.json`).
- Unit and integration test suite with 100% pass rate.
