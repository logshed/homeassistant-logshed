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
|       |-- config_flow.py       # Config flow, options flow, and reauth handler
|       |-- const.py             # Constants, config keys, defaults
|       |-- coordinator.py       # LogShedDataUpdateCoordinator (polling /api/v1/system/metrics)
|       |-- entity.py            # Base LogShedEntity (CoordinatorEntity subclass)
|       |-- manifest.json        # Integration manifest
|       |-- sensor.py            # LTS & diagnostic sensors (ingestion rate, errors, storage, etc.)
|       |-- services.py          # logshed.enable_maintenance, logshed.disable_maintenance
|       |-- services.yaml        # Service schemas & descriptions for HA Developer Tools
|       |-- switch.py            # Maintenance mode switch
|       |-- strings.json         # Base localization strings
|       `-- translations/
|           `-- en.json          # English translation strings
|-- tests/
|   |-- __init__.py
|   |-- conftest.py              # HA fixtures & mock aiohttp responses
|   |-- test_api.py              # REST API client tests
|   |-- test_binary_sensor.py    # Binary sensor tests
|   |-- test_button.py           # Button tests
|   |-- test_config_flow.py      # Config flow, options, reauth tests
|   |-- test_coordinator.py      # Polling and error handling tests
|   |-- test_init.py             # Setup and unload lifecycle tests
|   |-- test_sensor.py           # Sensor state & extra attribute verification
|   |-- test_services.py         # Service call execution tests
|   `-- test_switch.py           # Switch control tests
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
- Set unique ID from `instance_id` (fallback to normalized `host:port`) to avoid duplicate entries and preserve entity history across IP changes.
- Implement Reauth Flow for 401/403 token expirations and Options Flow for runtime settings (polling interval, default maintenance duration, and log handling mode). Do not set `self.config_entry` directly in `OptionsFlow.__init__` as that setter is deprecated in modern HA.

### D. Entities & State Management
- **Sensors:** Declare explicit `state_class` (`SensorStateClass.MEASUREMENT`, `TOTAL`, or `TOTAL_INCREASING`) and `device_class` (`SensorDeviceClass.DATA_SIZE`, `DURATION`, etc.) so Home Assistant Long-Term Statistics (LTS) track them automatically. Disk Used Percent uses icon `mdi:chart-pie`.
- **Attributes:** Rolling error sensors (`sensor.logshed_error_count_24h` and `1h`) must provide breakdown attributes: `top_error_apps` and `top_error_hosts` (`[{"name": "...", "count": N}]`).
- **Binary Sensors:** Problem device class for `binary_sensor.logshed_alert_state` (15-minute sliding window), `connectivity` for polling status, and custom for active maintenance.
- **Device Info:** Group all entities under a unified LogShed device entry via `DeviceInfo(identifiers={(DOMAIN, instance_id)}, ...)` so they appear cleanly under **Settings > Devices & Services**.

### E. Translations & Strings
- Never hardcode user-visible UI labels in Python files.
- Put strings in `strings.json` and generate or update `translations/en.json`.

---

## 4. Coding Standards

- **Python Version:** Python 3.12+ compatible.
- **Typing:** Use type annotations (`typing`) across all signatures.
- **Error Handling:** Map HTTP and network errors to standard Home Assistant exceptions:
  - `CannotConnect` on network unreachable / timeout.
  - `InvalidAuth` on 401 / 403 HTTP responses.
  - `UpdateFailed` inside coordinator `_async_update_data`.
- **Logging:** Use `_LOGGER = logging.getLogger(__name__)`. Do not log sensitive API tokens.

---

## 5. Testing & Verification

- Tests live in `tests/` and use `pytest-homeassistant-custom-component`.
- Mock external network calls with `aiohttp` mocking fixtures or `unittest.mock`.
- Ensure tests cover:
  - Config flow (user input, connection error, invalid auth, duplicate host, reauth).
  - Coordinator updates and graceful degradation on network outage.
  - Entity state calculations and attribute schemas.
  - Service action calls (`logshed.enable_maintenance`, `logshed.disable_maintenance`).
- Must pass Home Assistant `hassfest` validation and `HACS Action` before release.
