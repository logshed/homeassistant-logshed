"""Tests for LogShed switch platform."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
)

from custom_components.logshed.api import (
    LogShedApiClient,
    LogShedAuthInfo,
    LogShedInvalidAuth,
    LogShedMetrics,
    LogShedNotFound,
)
from custom_components.logshed.const import DOMAIN

from .conftest import MOCK_SESSION_UNTIL, setup_integration

ENTITY_ID = "switch.logshed_quick_maintenance"


async def _call(hass: HomeAssistant, service: str) -> None:
    await hass.services.async_call(SWITCH_DOMAIN, service, {"entity_id": ENTITY_ID}, blocking=True)


async def test_switch_off_for_maintenance_started_elsewhere(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test maintenance started elsewhere (or scheduled) does not turn the switch on."""
    await setup_integration(hass, mock_config_entry, mock_api_client, [Platform.SWITCH])

    assert mock_config_entry.runtime_data.coordinator.data.maintenance_active is True
    assert hass.states.get(ENTITY_ID).state == "off"

    # Turning it off does not end sessions the switch did not start
    await _call(hass, "turn_off")
    mock_api_client.async_disable_maintenance.assert_not_awaited()


async def test_switch_turn_on_and_off_own_session(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test the switch starts a session and ends only that session."""
    await setup_integration(hass, mock_config_entry, mock_api_client, [Platform.SWITCH])

    await _call(hass, "turn_on")
    mock_api_client.async_enable_maintenance.assert_awaited_once_with(
        duration_minutes=60,
        reason="Home Assistant Quick Maintenance",
        log_handling="silence_alerts",
    )
    assert hass.states.get(ENTITY_ID).state == "on"

    # Turning on again while the session runs does not start another one
    await _call(hass, "turn_on")
    assert mock_api_client.async_enable_maintenance.await_count == 1

    await _call(hass, "turn_off")
    mock_api_client.async_disable_maintenance.assert_awaited_once_with(session_id="sess-123")
    assert hass.states.get(ENTITY_ID).state == "off"


async def test_switch_turn_off_session_already_ended(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test a 404 on turn off (session already ended) counts as success."""
    await setup_integration(hass, mock_config_entry, mock_api_client, [Platform.SWITCH])
    await _call(hass, "turn_on")

    mock_api_client.async_disable_maintenance = AsyncMock(side_effect=LogShedNotFound("gone"))
    await _call(hass, "turn_off")
    assert hass.states.get(ENTITY_ID).state == "off"


async def test_switch_forgets_session_when_maintenance_ends(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
    mock_metrics: LogShedMetrics,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the switch turns off once LogShed reports no active maintenance."""
    await setup_integration(hass, mock_config_entry, mock_api_client, [Platform.SWITCH])
    coordinator = mock_config_entry.runtime_data.coordinator
    await _call(hass, "turn_on")

    # A poll already in flight when the session started is ignored
    mock_metrics.maintenance_active = False
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == "on"

    freezer.tick(timedelta(seconds=20))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == "off"

    # The session is forgotten, so turning off makes no API call
    await _call(hass, "turn_off")
    mock_api_client.async_disable_maintenance.assert_not_awaited()


async def test_switch_turns_off_when_session_expires(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the switch turns off when its session's end time passes."""
    mock_api_client.async_enable_maintenance = AsyncMock(
        return_value={"session_id": "sess-1", "until": "2026-10-20T13:00:00+00:00"}
    )
    freezer.move_to("2026-10-20T12:00:00+00:00")
    await setup_integration(hass, mock_config_entry, mock_api_client, [Platform.SWITCH])
    await _call(hass, "turn_on")
    assert hass.states.get(ENTITY_ID).state == "on"

    freezer.move_to("2026-10-20T13:00:01+00:00")
    await mock_config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == "off"


async def test_switch_restores_session(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test the switch keeps its session across a Home Assistant restart."""
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(ENTITY_ID, "on"),
                {"session_id": "sess-restored", "until": MOCK_SESSION_UNTIL},
            )
        ],
    )
    await setup_integration(hass, mock_config_entry, mock_api_client, [Platform.SWITCH])
    assert hass.states.get(ENTITY_ID).state == "on"

    await _call(hass, "turn_off")
    mock_api_client.async_disable_maintenance.assert_awaited_once_with(session_id="sess-restored")


async def test_switch_drops_expired_restored_session(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test a restored session whose end time has passed is discarded."""
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(ENTITY_ID, "on"),
                {"session_id": "sess-old", "until": "2020-01-01T00:00:00+00:00"},
            )
        ],
    )
    await setup_integration(hass, mock_config_entry, mock_api_client, [Platform.SWITCH])
    assert hass.states.get(ENTITY_ID).state == "off"

    await _call(hass, "turn_off")
    mock_api_client.async_disable_maintenance.assert_not_awaited()


async def test_switch_not_created_without_maintenance_write(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test the switch needs the maintenance:write scope."""
    mock_api_client.async_verify_auth = AsyncMock(
        return_value=LogShedAuthInfo(
            valid=True, name="Read only", scopes=["system:*"], expires_at=None
        )
    )
    await setup_integration(hass, mock_config_entry, mock_api_client, [Platform.SWITCH])

    assert hass.states.get(ENTITY_ID) is None


SCOPE_ERROR = "Insufficient token scope. Required: maintenance:write"


async def test_switch_turn_on_reports_a_scope_removed_after_setup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test a token that lost maintenance:write since setup gives a clear error, not a reauth."""
    await setup_integration(hass, mock_config_entry, mock_api_client, [Platform.SWITCH])
    mock_api_client.async_enable_maintenance = AsyncMock(
        side_effect=LogShedInvalidAuth(SCOPE_ERROR)
    )

    with pytest.raises(HomeAssistantError, match="Required: maintenance:write"):
        await _call(hass, "turn_on")

    assert hass.states.get(ENTITY_ID).state == "off"
    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)


async def test_switch_turn_off_reports_a_scope_removed_after_setup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: LogShedApiClient,
) -> None:
    """Test ending the session with a token that lost maintenance:write keeps the switch on."""
    await setup_integration(hass, mock_config_entry, mock_api_client, [Platform.SWITCH])
    await _call(hass, "turn_on")
    mock_api_client.async_disable_maintenance = AsyncMock(
        side_effect=LogShedInvalidAuth(SCOPE_ERROR)
    )

    with pytest.raises(HomeAssistantError, match="Required: maintenance:write"):
        await _call(hass, "turn_off")

    # The session was not ended on the server
    assert hass.states.get(ENTITY_ID).state == "on"
    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)
