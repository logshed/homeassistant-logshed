# Changelog

All notable changes to the LogShed Home Assistant integration will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-16

### Added
- Initial release of the official LogShed Home Assistant custom integration. Requires Home Assistant 2024.12.0 or later and LogShed 1.3.0 or later.
- Dedicated UI config flow with Bearer token authentication (`ls_live_...`), token scope verification, and SSL verification options. Adding an instance that is already configured updates its host URL and SSL setting.
- Reconfigure flow to change the host URL and SSL verification of an entry; it refuses a server that is a different LogShed instance.
- Dynamic options flow to configure metrics polling interval (10 to 300s), default maintenance duration (5 to 720 min), and default maintenance log handling mode (`silence_alerts` or `drop_errors`).
- Reauthentication flow handling expired or rotated API tokens with automatic reload; a token for a different LogShed instance is refused.
- Scope-aware entities: token scopes are read from `/api/v1/auth/verify` each time the entry loads. The Quick Maintenance switch needs `maintenance:write` and the prune and vacuum buttons need `system:write`; without the scope they are not created, and the maintenance actions fail with a clear error.
- `LogShedDataUpdateCoordinator` polling `/api/v1/system/metrics` with automatic error propagation and offline state handling.
- The device is named after the LogShed server name, and default entity IDs follow it (`sensor.logshed_*` with the default name `LogShed`).
- 17 sensor entities for real-time and Long-Term Statistics (LTS):
  - Ingestion Rate (`logs/s`)
  - Rolling 24-hour and 1-hour Error or Worse Logs (severities 0 to 3 combined) with top offending applications (`top_error_apps`) and hosts (`top_error_hosts`)
  - Rolling 24-hour log counts per severity: Emergency, Alert, Critical, Error and Warning
  - Total Stored Logs
  - Database Size and Disk Free, reported in bytes and shown in MB and GB by default (`data_size`, so the unit can be changed)
  - Disk Used Percent (`%`)
  - In-memory Queue Depth
  - Dropped Logs & Filtered Logs
  - UDP Lost (`datagrams`): UDP syslog datagrams the kernel discarded because LogShed's receive buffer was full, unknown when LogShed cannot read the counter
  - Maintenance Remaining, reported in seconds and shown in whole minutes by default (`duration`, so the unit can be changed)
- The rolling log counts (Error or Worse Logs and the per-severity counts) use the `measurement` state class, since they rise and fall as logs leave the window.
- Server health sensors (Database Size, Disk Free, Disk Used Percent, Queue Depth, Dropped Logs, Filtered Logs and UDP Lost) are diagnostic entities, so the device page keeps the log activity sensors together.
- 3 binary sensors:
  - Alert State (sliding 15-minute problem state class)
  - Maintenance Active (any maintenance, including other sources and scheduled windows, with session attributes: `until`, `active_sessions_count`, `log_handling`)
  - Connectivity status (diagnostic; reports off, not unavailable, when LogShed cannot be reached)
- Quick Maintenance switch (`switch.logshed_quick_maintenance`) that starts a maintenance window with the default options: it is on only while that window runs and turning it off ends only that window. Windows from `logshed.enable_maintenance`, the web UI, MCP clients or schedules never turn it on. The window is kept across Home Assistant restarts.
- Diagnostic buttons for manual maintenance:
  - Prune Database (with 409 conflict and 429 rate limit cooldown handling)
  - Vacuum Database (also reports insufficient disk space)
  - Both wait up to 10 minutes for LogShed and, on timeout, say the operation may still be running on the server.
- Home Assistant service actions, registered once for the integration and targeted with an optional `config_entry_id` (all loaded instances when omitted):
  - `logshed.enable_maintenance`: Start targeted maintenance windows with custom duration, reason, target app/host filters, and log handling modes. Returns the started sessions (`config_entry_id`, `session_id`, `until`) for use with `response_variable`.
  - `logshed.disable_maintenance`: End the session given by `session_id`, or every active on-demand session when omitted.
- API errors are reported precisely: `404` as not found, `422` validation messages joined into one message, and other `4xx` responses with their status code instead of a network error.
- Update entity (`update.logshed_update`) showing the installed LogShed version and the latest stable release from `/api/v1/system/version`, with a link to the release notes. It is checked once an hour, follows LogShed's own version comparison, shows unknown when LogShed's update check is off or failed, and is not created for a server without the endpoint.
- Config entry diagnostics with the API token redacted.
- Local brand proxy assets (`brand/icon.png`, `brand/logo.png`) complying with Home Assistant 2026.3+ specifications.
- Full English translations (`strings.json`, `translations/en.json`).
- Unit and integration test suite with 100% pass rate.
