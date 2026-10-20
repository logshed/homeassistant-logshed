"""The LogShed integration."""

from __future__ import annotations

import logging

from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import LogShedApiClient, LogShedError, LogShedInvalidAuth, has_scope
from .const import (
    CONF_API_TOKEN,
    CONF_VERIFY_SSL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    PLATFORMS,
    SCOPE_SYSTEM_READ,
)
from .coordinator import LogShedConfigEntry, LogShedDataUpdateCoordinator, LogShedRuntimeData
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the LogShed integration (service actions are shared by all entries)."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: LogShedConfigEntry) -> bool:
    """Set up LogShed from a config entry."""
    host: str = entry.data[CONF_HOST]
    api_token: str = entry.data[CONF_API_TOKEN]
    verify_ssl: bool = entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)

    session = async_get_clientsession(hass, verify_ssl=verify_ssl)
    api = LogShedApiClient(
        host=host,
        api_token=api_token,
        session=session,
        verify_ssl=verify_ssl,
    )

    # Scopes can change on the server after setup, so read them on every load.
    try:
        auth_info = await api.async_verify_auth()
    except LogShedInvalidAuth as err:
        raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
    except LogShedError as err:
        raise ConfigEntryNotReady(f"Cannot connect to LogShed: {err}") from err
    if not auth_info.valid or not has_scope(auth_info.scopes, SCOPE_SYSTEM_READ):
        raise ConfigEntryAuthFailed(f"The API token lacks the '{SCOPE_SYSTEM_READ}' scope")

    coordinator = LogShedDataUpdateCoordinator(hass, api, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = LogShedRuntimeData(coordinator=coordinator, scopes=auth_info.scopes)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: LogShedConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: LogShedConfigEntry) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
