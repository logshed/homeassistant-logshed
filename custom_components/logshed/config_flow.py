"""Config flow for LogShed integration."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    LogShedApiClient,
    LogShedCannotConnect,
    LogShedInvalidAuth,
    LogShedMetrics,
)
from .const import (
    CONF_API_TOKEN,
    CONF_MAINTENANCE_DURATION,
    CONF_MAINTENANCE_LOG_HANDLING,
    CONF_SCAN_INTERVAL,
    CONF_VERIFY_SSL,
    DEFAULT_MAINTENANCE_DURATION,
    DEFAULT_MAINTENANCE_LOG_HANDLING,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    LOG_HANDLING_DROP_ERRORS,
    LOG_HANDLING_SILENCE_ALERTS,
    MAX_MAINTENANCE_DURATION,
    MAX_SCAN_INTERVAL,
    MIN_MAINTENANCE_DURATION,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


def _has_scope(granted_scopes: list[str], target: str) -> bool:
    """Check if target scope is covered by granted scopes."""
    if "*" in granted_scopes:
        return True
    category = target.split(":")[0]
    if f"{category}:*" in granted_scopes:
        return True
    return target in granted_scopes


def _normalize_host(host: str) -> str:
    """Normalize and validate host URL."""
    cleaned = host.strip().rstrip("/")
    if not cleaned.startswith(("http://", "https://")):
        cleaned = f"http://{cleaned}"
    parsed = urlparse(cleaned)
    if not parsed.netloc:
        raise ValueError("Invalid host URL")
    return cleaned


class LogShedConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for LogShed."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        self._reauth_entry: ConfigEntry | None = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlow:
        """Get the options flow for this handler."""
        return LogShedOptionsFlowHandler()

    async def _validate_input(self, data: dict[str, Any]) -> tuple[dict[str, Any], LogShedMetrics]:
        """Validate the user input by connecting to the LogShed instance."""
        host = _normalize_host(data[CONF_HOST])
        token = data[CONF_API_TOKEN].strip()
        verify_ssl = data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)

        session = async_get_clientsession(self.hass, verify_ssl=verify_ssl)
        client = LogShedApiClient(
            host=host, api_token=token, session=session, verify_ssl=verify_ssl
        )

        # 1. Verify token & scopes
        auth_info = await client.async_verify_auth()
        if not auth_info.valid or not _has_scope(auth_info.scopes, "system:read"):
            raise LogShedInvalidAuth("Token does not have required 'system:read' scope")

        if not _has_scope(auth_info.scopes, "maintenance:write"):
            _LOGGER.warning(
                "LogShed token '%s' is missing 'maintenance:write' scope; maintenance controls will be unavailable",
                auth_info.name,
            )
        if not _has_scope(auth_info.scopes, "system:write"):
            _LOGGER.warning(
                "LogShed token '%s' is missing 'system:write' scope; prune and vacuum buttons will be unavailable",
                auth_info.name,
            )

        # 2. Fetch system metrics to retrieve instance_id and server_name
        metrics = await client.async_get_system_metrics()
        normalized_data = {
            CONF_HOST: host,
            CONF_API_TOKEN: token,
            CONF_VERIFY_SSL: verify_ssl,
            CONF_MAINTENANCE_DURATION: int(
                data.get(CONF_MAINTENANCE_DURATION, DEFAULT_MAINTENANCE_DURATION)
            ),
        }
        return normalized_data, metrics

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                normalized_data, metrics = await self._validate_input(user_input)
            except ValueError:
                errors["base"] = "invalid_host"
            except LogShedInvalidAuth:
                errors["base"] = "invalid_auth"
            except LogShedCannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during LogShed setup")
                errors["base"] = "unknown"
            else:
                unique_id = metrics.instance_id or normalized_data[CONF_HOST]
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                title = f"LogShed ({metrics.server_name})"
                options = {
                    CONF_MAINTENANCE_DURATION: normalized_data[CONF_MAINTENANCE_DURATION],
                    CONF_MAINTENANCE_LOG_HANDLING: DEFAULT_MAINTENANCE_LOG_HANDLING,
                }
                return self.async_create_entry(title=title, data=normalized_data, options=options)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOST,
                    default=user_input.get(CONF_HOST, "") if user_input else "",
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
                vol.Required(CONF_API_TOKEN): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Required(
                    CONF_VERIFY_SSL,
                    default=user_input.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
                    if user_input
                    else DEFAULT_VERIFY_SSL,
                ): BooleanSelector(),
                vol.Optional(
                    CONF_MAINTENANCE_DURATION,
                    default=user_input.get(CONF_MAINTENANCE_DURATION, DEFAULT_MAINTENANCE_DURATION)
                    if user_input
                    else DEFAULT_MAINTENANCE_DURATION,
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_MAINTENANCE_DURATION,
                        max=MAX_MAINTENANCE_DURATION,
                        step=5,
                        unit_of_measurement="min",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Perform reauth upon an API authentication failure."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Dialog that prompts user for new API token."""
        errors: dict[str, str] = {}
        entry = self._reauth_entry or self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )

        if user_input is not None and entry is not None:
            new_data = dict(entry.data)
            new_data[CONF_API_TOKEN] = user_input[CONF_API_TOKEN].strip()

            try:
                _, _ = await self._validate_input(new_data)
            except LogShedInvalidAuth:
                errors["base"] = "invalid_auth"
            except LogShedCannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during reauth")
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(entry, data=new_data)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        schema = vol.Schema(
            {
                vol.Required(CONF_API_TOKEN): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
            }
        )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
        )


class LogShedOptionsFlowHandler(OptionsFlow):
    """Handle options flow for LogShed integration."""

    def __init__(self, config_entry: ConfigEntry | None = None) -> None:
        """Initialize LogShed options flow."""
        if config_entry is not None:
            self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        scan_interval = int(options.get(CONF_SCAN_INTERVAL) or DEFAULT_SCAN_INTERVAL)
        maintenance_duration = int(
            options.get(CONF_MAINTENANCE_DURATION)
            or self.config_entry.data.get(CONF_MAINTENANCE_DURATION)
            or DEFAULT_MAINTENANCE_DURATION
        )
        log_handling = (
            options.get(CONF_MAINTENANCE_LOG_HANDLING) or DEFAULT_MAINTENANCE_LOG_HANDLING
        )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=scan_interval,
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=5,
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_MAINTENANCE_DURATION,
                    default=maintenance_duration,
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_MAINTENANCE_DURATION,
                        max=MAX_MAINTENANCE_DURATION,
                        step=5,
                        unit_of_measurement="min",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_MAINTENANCE_LOG_HANDLING,
                    default=log_handling,
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(
                                value=LOG_HANDLING_SILENCE_ALERTS,
                                label="Silence alerts only",
                            ),
                            SelectOptionDict(
                                value=LOG_HANDLING_DROP_ERRORS,
                                label="Silence alerts & drop error logs",
                            ),
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
