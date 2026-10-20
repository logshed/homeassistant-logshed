"""Config flow for LogShed integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
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
    has_scope,
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
    SCOPE_MAINTENANCE_WRITE,
    SCOPE_SYSTEM_READ,
    SCOPE_SYSTEM_WRITE,
)

_LOGGER = logging.getLogger(__name__)


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
        if not auth_info.valid or not has_scope(auth_info.scopes, SCOPE_SYSTEM_READ):
            raise LogShedInvalidAuth(f"Token does not have required '{SCOPE_SYSTEM_READ}' scope")

        if not has_scope(auth_info.scopes, SCOPE_MAINTENANCE_WRITE):
            _LOGGER.warning(
                "LogShed token '%s' is missing the '%s' scope; the Quick Maintenance switch will not "
                "be created and the maintenance service actions will fail",
                auth_info.name,
                SCOPE_MAINTENANCE_WRITE,
            )
        if not has_scope(auth_info.scopes, SCOPE_SYSTEM_WRITE):
            _LOGGER.warning(
                "LogShed token '%s' is missing the '%s' scope; the prune and vacuum buttons "
                "will not be created",
                auth_info.name,
                SCOPE_SYSTEM_WRITE,
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

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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
                # A known instance at a new address keeps its entry and history
                self._abort_if_unique_id_configured(
                    updates={
                        CONF_HOST: normalized_data[CONF_HOST],
                        CONF_VERIFY_SSL: normalized_data[CONF_VERIFY_SSL],
                    }
                )

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

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the host URL or SSL verification of an existing entry."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            new_data = {
                **entry.data,
                CONF_HOST: user_input[CONF_HOST],
                CONF_VERIFY_SSL: user_input[CONF_VERIFY_SSL],
            }
            try:
                normalized_data, metrics = await self._validate_input(new_data)
            except ValueError:
                errors["base"] = "invalid_host"
            except LogShedInvalidAuth:
                errors["base"] = "invalid_auth"
            except LogShedCannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during LogShed reconfigure")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(metrics.instance_id)
                self._abort_if_unique_id_mismatch(reason="wrong_instance")
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_HOST: normalized_data[CONF_HOST],
                        CONF_VERIFY_SSL: normalized_data[CONF_VERIFY_SSL],
                    },
                )

        current = user_input or entry.data
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=current.get(CONF_HOST, "")): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.URL)
                ),
                vol.Required(
                    CONF_VERIFY_SSL,
                    default=current.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
                ): BooleanSelector(),
            }
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Perform reauth upon an API authentication failure."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Dialog that prompts user for new API token."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            new_data = dict(entry.data)
            new_data[CONF_API_TOKEN] = user_input[CONF_API_TOKEN].strip()

            try:
                _, metrics = await self._validate_input(new_data)
            except LogShedInvalidAuth:
                errors["base"] = "invalid_auth"
            except LogShedCannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during reauth")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(metrics.instance_id)
                self._abort_if_unique_id_mismatch(reason="wrong_instance")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_TOKEN: new_data[CONF_API_TOKEN]}
                )

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

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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
