# AGENTS.md — Developer & AI Agent Guidelines

Welcome to `homeassistant-logshed`. This repository contains the official Home Assistant Community Store (HACS) custom integration for **LogShed**.

---

## 1. Project Context & Purpose

- **Repository:** `logshed/homeassistant-logshed` (Remote: `https://github.com/logshed/homeassistant-logshed`)
- **Integration Domain:** `logshed`
- **Component Path:** `custom_components/logshed/`
- **Purpose:** Connects Home Assistant instances with LogShed (v1.3.0+) via its external REST API to provide real-time log ingestion metrics, error tracking with top offending services, storage stats, automated maintenance window controls, diagnostic buttons, and problem alert sensors.
- **External LogShed Codebase:** The core LogShed server codebase resides in `../logshed`. **Important:** Do not modify any files in `../logshed`. Use it solely as reference for data schemas and endpoints if needed. All integration work belongs strictly inside this repository.

---

## 2. Target Repository Structure

```
homeassistant-logshed/
|-- .github/
|   `-- workflows/
|       |-- validate.yml         # hassfest and HACS action validation
|       |-- test.yml             # pytest test suite execution
|       `-- release.yml          # GitHub release workflow for semver tags
|-- custom_components/
|   `-- logshed/
|       |-- brand/               # Local brand proxy assets (HA 2026.3+)
|       |   |-- icon.png
|       |   |-- icon@2x.png
|       |   |-- logo.png
|       |   `-- logo@2x.png
|       |-- __init__.py          # Entry setup, coordinator lifecycle, platform forwarding
|       |-- api.py               # Asynchronous LogShed REST API client (aiohttp)
|       |-- binary_sensor.py     # Alert state, maintenance active, connectivity sensors
|       |-- button.py            # Diagnostic buttons (prune database, vacuum database)
|       |-- config_flow.py       # Config flow, options flow, reauth and reconfigure
|       |-- const.py             # Constants, config keys, defaults
|       |-- coordinator.py       # Metrics coordinator (/api/v1/system/metrics) and version coordinator (/api/v1/system/version)
|       |-- diagnostics.py       # Config entry diagnostics (API token redacted)
|       |-- entity.py            # Base LogShedEntity (CoordinatorEntity subclass)
|       |-- manifest.json        # Integration manifest
|       |-- sensor.py            # LTS & diagnostic sensors (ingestion rate, errors, storage, etc.)
|       |-- services.py          # logshed.enable_maintenance, logshed.disable_maintenance
|       |-- services.yaml        # Service schemas & descriptions for HA Developer Tools
|       |-- switch.py            # Maintenance mode switch (the session Home Assistant started)
|       |-- update.py            # Update entity (LogShed version and latest stable release)
|       |-- strings.json         # Base localization strings
|       `-- translations/
|           `-- en.json          # English translation strings
|-- tests/
|   |-- __init__.py
|   |-- conftest.py              # HA fixtures & mock aiohttp responses
|   |-- test_api.py              # REST API client tests
|   |-- test_binary_sensor.py    # Binary sensor tests
|   |-- test_button.py           # Button tests
|   |-- test_config_flow.py      # Config flow, options, reauth, reconfigure tests
|   |-- test_coordinator.py      # Polling and error handling tests
|   |-- test_diagnostics.py      # Diagnostics redaction tests
|   |-- test_init.py             # Setup and unload lifecycle tests
|   |-- test_sensor.py           # Sensor state & extra attribute verification
|   |-- test_services.py         # Service call execution tests
|   |-- test_switch.py           # Switch control tests
|   `-- test_update.py           # Update entity tests
|-- CHANGELOG.md                 # Project version changelog (Keep a Changelog)
|-- hacs.json                    # HACS repository metadata
|-- icon.png                     # Repository brand icon
|-- logo.png                     # Repository brand logo
|-- pyproject.toml               # Development dependencies, ruff & pytest config
`-- README.md                    # Installation instructions, Lovelace snippets, automations
```

---

## 3. Core Architecture & Requirements

### A. Data Polling & Coordinator
- Polling uses `LogShedDataUpdateCoordinator` (inheriting from `DataUpdateCoordinator`).
- Default scan interval is 30 seconds (configurable via Options Flow between 10s and 300s).
- `LogShedVersionCoordinator` polls `GET /api/v1/system/version` once an hour (LogShed caches its GHCR check for 1 hour), separate from the metrics poll. Its first refresh must not block setup; a `404` sets `endpoint_missing` and the update entity is not created (`runtime_data.version_coordinator` is `None`).
- The update entity (`update.logshed_update`, Diagnostic, no install feature) overrides `version_is_newer` with LogShed's `update_available`, so pre-release installs compare as LogShed compares them. `latest_version` is `None` (unknown) when LogShed's check is off or failed.
- All entity platforms (`sensor`, `binary_sensor`, `switch`, etc.) inherit from `CoordinatorEntity`.

### B. Asynchronous Networking
- Always use `aiohttp` via `homeassistant.helpers.aiohttp_client.async_get_clientsession(hass)` for HTTP requests.
- Never use blocking libraries like `requests` or synchronous `urllib`.
- Never perform blocking I/O on the main event loop.

### C. Config Flow & Authentication
- Setup is strictly UI-based via `config_flow.py` (`"config_flow": true` in `manifest.json` is mandatory for HACS default inclusion).
- Collects:
  - `host`: LogShed instance URL (e.g., `http://192.168.1.100:8000`)
  - `api_token`: Bearer token (`ls_live_...`)
  - `verify_ssl`: Boolean (default `True`, toggleable for self-signed certificates)
  - `default_maintenance_duration`: Integer in minutes (default `60`, range 5 to 720)
- Validates credentials via `GET /api/v1/auth/verify` and fetches initial system info from `GET /api/v1/system/metrics`.
- Set unique ID from `instance_id` (fallback to normalized `host:port`) to avoid duplicate entries and preserve entity history across IP changes. Re-adding a known instance updates its `host` and `verify_ssl` (`_abort_if_unique_id_configured(updates=...)`).
- Implement Reauth Flow for 401/403 token expirations, a Reconfigure Flow for host and SSL verification, and Options Flow for runtime settings (polling interval, default maintenance duration, and log handling mode). Reauth and reconfigure abort with `wrong_instance` when the server's `instance_id` differs (`_abort_if_unique_id_mismatch`). Do not set `self.config_entry` in `OptionsFlow`; Home Assistant provides it (2024.12+).
- `async_setup_entry` reads the token's scopes from `GET /api/v1/auth/verify` on every load and stores them with the coordinator in `entry.runtime_data` (`LogShedRuntimeData`, typed `LogShedConfigEntry`). Never use `hass.data[DOMAIN]`. Check scopes with `has_scope` in `api.py`.
- Minimum Home Assistant version is set in `hacs.json` (currently `2024.12.0`, for the automatic `OptionsFlow.config_entry`). Raise it when using newer Home Assistant APIs.

### D. Entities & State Management
- **Sensors:** Declare explicit `state_class` (`SensorStateClass.MEASUREMENT`, `TOTAL`, or `TOTAL_INCREASING`) and `device_class` (`SensorDeviceClass.DATA_SIZE`, `DURATION`, etc.) so Home Assistant Long-Term Statistics (LTS) track them automatically. Rolling window counts (error or worse 24h and 1h, per-severity 24h) rise and fall, so they are `MEASUREMENT`, never `TOTAL`. Counters since LogShed started (dropped, filtered, UDP lost) are `TOTAL_INCREASING`. Sizes report bytes (`UnitOfInformation.BYTES`) with `suggested_unit_of_measurement` (MB for database size, GB for disk free), so Home Assistant converts them. Disk Used Percent uses icon `mdi:chart-pie`. UDP Lost (`udp_lost`) is `None` (unknown) when LogShed returns `null`.
- **Entity Categories:** Server health sensors (database size, disk free, disk used percent, queue depth, dropped logs, filtered logs, UDP lost), the connectivity binary sensor, and the prune and vacuum buttons use `EntityCategory.DIAGNOSTIC`; log activity sensors have no category, so they sit together in the Sensors card.
- **Scopes:** Create the Quick Maintenance switch only with `maintenance:write`, and the prune and vacuum buttons only with `system:write`. The maintenance services raise `ServiceValidationError` when a targeted instance's token lacks `maintenance:write`.
- **Quick Maintenance Switch:** `switch.logshed_quick_maintenance` (key `quick_maintenance`) starts a window with the options flow defaults and represents only that session; sessions from `logshed.enable_maintenance`, the web UI, MCP or schedules never turn it on. `turn_on` stores the returned `session_id` and `until` (persisted with `RestoreEntity` extra data); `turn_off` ends only that session (`404` counts as success). It is on while its session is stored, `until` is in the future and LogShed reports maintenance active. `binary_sensor.logshed_maintenance_active` is the "any maintenance, including scheduled" indicator.
- **Services:** Registered once in `async_setup` (`CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)`), targeted by an optional `config_entry_id` (all loaded entries when omitted). `logshed.enable_maintenance` supports an optional response `{"sessions": [{"config_entry_id", "session_id", "until"}]}`.
- **Attributes:** Rolling error or worse sensors (`sensor.logshed_error_or_worse_logs_24h` and `1h`, severities 0 to 3 combined) must provide breakdown attributes: `top_error_apps` and `top_error_hosts` (`[{"name": "...", "count": N}]`).
- **Binary Sensors:** Problem device class for `binary_sensor.logshed_alert_state` (15-minute sliding window), `connectivity` for polling status (always available, so a failed poll shows `off`), and custom for active maintenance.
- **Device Info:** Group all entities under a unified LogShed device entry via `DeviceInfo(identifiers={(DOMAIN, instance_id)}, ...)` so they appear cleanly under **Settings > Devices & Services**. The device name is the LogShed `server_name` (default "LogShed"), so default entity IDs follow it.

### E. Translations & Strings
- Never hardcode user-visible UI labels in Python files.
- Put strings in `strings.json` and generate or update `translations/en.json`.

---

## 4. Coding Standards

- **Python Version:** Python 3.12+ compatible.
- **Typing:** Use type annotations (`typing`) across all signatures.
- **Error Handling:** Map HTTP and network errors to standard Home Assistant exceptions:
  - `CannotConnect` on network unreachable / timeout. Only network failures map here, never an HTTP status.
  - `InvalidAuth` on 401 / 403 HTTP responses.
  - `NotFound` on 404, `BadRequest` on 400 and 422 (FastAPI validation `msg` values joined), `Conflict` on 409, `RateLimited` on 429, `ServerError` on 5xx, and `LogShedError` with the status for any other 4xx.
  - Prune and vacuum use `LONG_OPERATION_TIMEOUT` (600 s) because LogShed runs them inside the request; their timeout raises `LogShedOperationTimeout` (may still be running on the server). Other requests use `DEFAULT_REQUEST_TIMEOUT` (15 s).
  - `UpdateFailed` inside coordinator `_async_update_data`.
- **Logging:** Use `_LOGGER = logging.getLogger(__name__)`. Do not log sensitive API tokens.

---

## 5. Testing & Verification

- Tests live in `tests/` and use `pytest-homeassistant-custom-component`.
- Mock external network calls with `aiohttp` mocking fixtures or `unittest.mock`.
- Ensure tests cover:
  - Config flow (user input, connection error, invalid auth, duplicate host, reauth, reconfigure).
  - Coordinator updates and graceful degradation on network outage.
  - Entity state calculations and attribute schemas.
  - Service action calls (`logshed.enable_maintenance`, `logshed.disable_maintenance`).
- Must pass Home Assistant `hassfest` validation and `HACS Action` before release.
