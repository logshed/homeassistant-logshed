"""Switch platform for the LogShed integration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity
from homeassistant.util import dt as dt_util

from .api import LogShedConflict, LogShedNotFound
from .const import (
    CONF_MAINTENANCE_DURATION,
    CONF_MAINTENANCE_LOG_HANDLING,
    DEFAULT_MAINTENANCE_DURATION,
    DEFAULT_MAINTENANCE_LOG_HANDLING,
    DEFAULT_REQUEST_TIMEOUT,
    SCOPE_MAINTENANCE_WRITE,
)
from .coordinator import LogShedConfigEntry, LogShedDataUpdateCoordinator
from .entity import LogShedEntity

SWITCH_DESCRIPTION = SwitchEntityDescription(
    key="quick_maintenance",
    translation_key="quick_maintenance",
    icon="mdi:wrench",
)

# A metrics poll already in flight when the session starts can still report maintenance as
# inactive. No request outlives its timeout, so later results reflect the new session.
_START_GRACE = timedelta(seconds=DEFAULT_REQUEST_TIMEOUT)


def parse_until(value: Any) -> datetime | None:
    """Parse a LogShed 'until' timestamp as an aware UTC datetime."""
    if not isinstance(value, str) or not value:
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.UTC)
    return dt_util.as_utc(parsed)


@dataclass
class MaintenanceSwitchExtraData(ExtraStoredData):
    """The maintenance session started by the switch, kept across restarts."""

    session_id: str | None
    until: str | None

    def as_dict(self) -> dict[str, Any]:
        """Return a dict representation of the extra data."""
        return asdict(self)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LogShedConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up LogShed switch entity based on a config entry."""
    runtime = entry.runtime_data
    if not runtime.has_scope(SCOPE_MAINTENANCE_WRITE):
        return
    async_add_entities([LogShedQuickMaintenanceSwitch(runtime.coordinator, SWITCH_DESCRIPTION)])


class LogShedQuickMaintenanceSwitch(LogShedEntity, SwitchEntity, RestoreEntity):
    """Quick Maintenance switch, on while the maintenance window it started is active.

    Turning it off ends only that session, never sessions started elsewhere (web UI, MCP,
    other automations) or scheduled windows.
    """

    entity_description: SwitchEntityDescription

    def __init__(
        self,
        coordinator: LogShedDataUpdateCoordinator,
        description: SwitchEntityDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._session_id: str | None = None
        self._until: datetime | None = None
        self._started_at: datetime | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the session started before a Home Assistant restart."""
        await super().async_added_to_hass()
        if (extra := await self.async_get_last_extra_data()) is not None:
            data = extra.as_dict()
            self._session_id = data.get("session_id") or None
            self._until = parse_until(data.get("until"))
        if self._session_id and not self._session_is_live():
            self._clear_session()

    @property
    def extra_restore_state_data(self) -> MaintenanceSwitchExtraData:
        """Return the session to keep across restarts."""
        return MaintenanceSwitchExtraData(
            session_id=self._session_id,
            until=self._until.isoformat() if self._until else None,
        )

    def _session_is_live(self) -> bool:
        """Return True while the switch's own session is running."""
        if self._session_id is None or self._until is None:
            return False
        now = dt_util.utcnow()
        if self._until <= now:
            return False
        if self._started_at is not None and now - self._started_at < _START_GRACE:
            return True
        return bool(self.coordinator.data and self.coordinator.data.maintenance_active)

    def _clear_session(self) -> None:
        self._session_id = None
        self._until = None
        self._started_at = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Forget the session once it has expired or maintenance has ended."""
        if self._session_id and not self._session_is_live():
            self._clear_session()
        super()._handle_coordinator_update()

    @property
    def is_on(self) -> bool:
        """Return True while the maintenance window started by this switch is active."""
        return self._session_is_live()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start a maintenance window with the default options."""
        if self._session_is_live():
            return
        options = self.coordinator.config_entry.options
        data = self.coordinator.config_entry.data
        duration = int(
            options.get(
                CONF_MAINTENANCE_DURATION,
                data.get(CONF_MAINTENANCE_DURATION, DEFAULT_MAINTENANCE_DURATION),
            )
        )
        log_handling = options.get(
            CONF_MAINTENANCE_LOG_HANDLING,
            data.get(CONF_MAINTENANCE_LOG_HANDLING, DEFAULT_MAINTENANCE_LOG_HANDLING),
        )

        try:
            result = await self.coordinator.api.async_enable_maintenance(
                duration_minutes=duration,
                reason="Home Assistant Quick Maintenance",
                log_handling=log_handling,
            )
        except LogShedConflict as err:
            raise HomeAssistantError(
                "Maximum active maintenance sessions limit (20) reached"
            ) from err

        self._session_id = result.get("session_id") or None
        self._until = parse_until(result.get("until"))
        self._started_at = dt_util.utcnow()
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """End the maintenance window started by this switch."""
        if self._session_id is None:
            return
        try:
            await self.coordinator.api.async_disable_maintenance(session_id=self._session_id)
        except LogShedNotFound:
            # The session has already ended or expired.
            pass

        self._clear_session()
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
