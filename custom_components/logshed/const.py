"""Constants for the LogShed integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "logshed"

PLATFORMS: Final = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
]

# Configuration and Option Keys
CONF_API_TOKEN: Final = "api_token"
CONF_VERIFY_SSL: Final = "verify_ssl"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_MAINTENANCE_DURATION: Final = "default_maintenance_duration"
CONF_MAINTENANCE_LOG_HANDLING: Final = "default_maintenance_log_handling"

# Default Values
DEFAULT_VERIFY_SSL: Final = True
DEFAULT_SCAN_INTERVAL: Final = 30  # seconds
MIN_SCAN_INTERVAL: Final = 10
MAX_SCAN_INTERVAL: Final = 300

DEFAULT_MAINTENANCE_DURATION: Final = 60  # minutes
MIN_MAINTENANCE_DURATION: Final = 5
MAX_MAINTENANCE_DURATION: Final = 720

DEFAULT_MAINTENANCE_LOG_HANDLING: Final = "silence_alerts"
LOG_HANDLING_SILENCE_ALERTS: Final = "silence_alerts"
LOG_HANDLING_DROP_ERRORS: Final = "drop_errors"

# Required and optional API scopes
REQUIRED_SCOPES: Final = {"system:read"}
OPTIONAL_MAINTENANCE_SCOPES: Final = {"maintenance:write"}
OPTIONAL_SYSTEM_WRITE_SCOPES: Final = {"system:write"}

# API Endpoints
ENDPOINT_AUTH_VERIFY: Final = "/api/v1/auth/verify"
ENDPOINT_SYSTEM_METRICS: Final = "/api/v1/system/metrics"
ENDPOINT_MAINTENANCE_ENABLE: Final = "/api/v1/maintenance/enable"
ENDPOINT_MAINTENANCE_DISABLE: Final = "/api/v1/maintenance/disable"
ENDPOINT_MAINTENANCE_STATUS: Final = "/api/v1/maintenance/status"
ENDPOINT_SYSTEM_PRUNE: Final = "/api/v1/system/prune"
ENDPOINT_SYSTEM_VACUUM: Final = "/api/v1/system/vacuum"

# Services
SERVICE_ENABLE_MAINTENANCE: Final = "enable_maintenance"
SERVICE_DISABLE_MAINTENANCE: Final = "disable_maintenance"
