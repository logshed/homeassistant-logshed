"""Tests for LogShed config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.logshed.api import (
    LogShedAuthInfo,
    LogShedCannotConnect,
    LogShedInvalidAuth,
    LogShedMetrics,
)
from custom_components.logshed.const import (
    CONF_API_TOKEN,
    CONF_MAINTENANCE_DURATION,
    CONF_MAINTENANCE_LOG_HANDLING,
    CONF_SCAN_INTERVAL,
    CONF_VERIFY_SSL,
    DOMAIN,
)

from .conftest import MOCK_HOST, MOCK_INSTANCE_ID, MOCK_TOKEN


async def test_user_flow_success(hass: HomeAssistant, mock_metrics: LogShedMetrics) -> None:
    """Test standard user setup flow successfully creates entry."""
    auth_info = LogShedAuthInfo(
        valid=True,
        name="Test Token",
        scopes=["*"],
        expires_at=None,
    )

    with (
        patch(
            "custom_components.logshed.config_flow.LogShedApiClient.async_verify_auth",
            AsyncMock(return_value=auth_info),
        ),
        patch(
            "custom_components.logshed.config_flow.LogShedApiClient.async_get_system_metrics",
            AsyncMock(return_value=mock_metrics),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: MOCK_HOST,
                CONF_API_TOKEN: MOCK_TOKEN,
                CONF_VERIFY_SSL: True,
            },
        )
        assert result2["type"] == FlowResultType.CREATE_ENTRY
        assert result2["title"] == "LogShed (TestShed)"
        assert result2["data"] == {
            CONF_HOST: MOCK_HOST,
            CONF_API_TOKEN: MOCK_TOKEN,
            CONF_VERIFY_SSL: True,
            CONF_MAINTENANCE_DURATION: 60,
        }
        assert result2["options"] == {
            CONF_MAINTENANCE_DURATION: 60,
            CONF_MAINTENANCE_LOG_HANDLING: "silence_alerts",
        }
        assert result2["result"].unique_id == MOCK_INSTANCE_ID


async def test_user_flow_invalid_host(hass: HomeAssistant) -> None:
    """Test user flow with an invalid host URL format."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "   ",
            CONF_API_TOKEN: MOCK_TOKEN,
            CONF_VERIFY_SSL: True,
        },
    )
    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"] == {"base": "invalid_host"}


async def test_user_flow_cannot_connect(hass: HomeAssistant) -> None:
    """Test user flow when connection fails."""
    with patch(
        "custom_components.logshed.config_flow.LogShedApiClient.async_verify_auth",
        AsyncMock(side_effect=LogShedCannotConnect("Connection refused")),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: MOCK_HOST,
                CONF_API_TOKEN: MOCK_TOKEN,
                CONF_VERIFY_SSL: True,
            },
        )
        assert result2["type"] == FlowResultType.FORM
        assert result2["errors"] == {"base": "cannot_connect"}


async def test_user_flow_invalid_auth(hass: HomeAssistant) -> None:
    """Test user flow when API token is invalid."""
    with patch(
        "custom_components.logshed.config_flow.LogShedApiClient.async_verify_auth",
        AsyncMock(side_effect=LogShedInvalidAuth("Invalid token")),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: MOCK_HOST,
                CONF_API_TOKEN: MOCK_TOKEN,
                CONF_VERIFY_SSL: True,
            },
        )
        assert result2["type"] == FlowResultType.FORM
        assert result2["errors"] == {"base": "invalid_auth"}


async def test_user_flow_missing_required_scope(hass: HomeAssistant) -> None:
    """Test user flow when token lacks system:read scope."""
    auth_info = LogShedAuthInfo(
        valid=True,
        name="Limited Token",
        scopes=["logs:read"],  # Missing system:read
        expires_at=None,
    )
    with patch(
        "custom_components.logshed.config_flow.LogShedApiClient.async_verify_auth",
        AsyncMock(return_value=auth_info),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: MOCK_HOST,
                CONF_API_TOKEN: MOCK_TOKEN,
                CONF_VERIFY_SSL: True,
            },
        )
        assert result2["type"] == FlowResultType.FORM
        assert result2["errors"] == {"base": "invalid_auth"}


async def test_user_flow_duplicate_aborted(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_metrics: LogShedMetrics
) -> None:
    """Test user flow aborts if instance is already configured."""
    mock_config_entry.add_to_hass(hass)
    auth_info = LogShedAuthInfo(
        valid=True,
        name="Test Token",
        scopes=["*"],
        expires_at=None,
    )

    with (
        patch(
            "custom_components.logshed.config_flow.LogShedApiClient.async_verify_auth",
            AsyncMock(return_value=auth_info),
        ),
        patch(
            "custom_components.logshed.config_flow.LogShedApiClient.async_get_system_metrics",
            AsyncMock(return_value=mock_metrics),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: MOCK_HOST,
                CONF_API_TOKEN: MOCK_TOKEN,
                CONF_VERIFY_SSL: True,
            },
        )
        assert result2["type"] == FlowResultType.ABORT
        assert result2["reason"] == "already_configured"


async def test_reauth_flow_success(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_metrics: LogShedMetrics
) -> None:
    """Test reauth flow updates entry token and reloads."""
    mock_config_entry.add_to_hass(hass)
    new_token = "ls_live_newupdatedtoken987654321"

    auth_info = LogShedAuthInfo(
        valid=True,
        name="Updated Token",
        scopes=["*"],
        expires_at=None,
    )

    with (
        patch(
            "custom_components.logshed.config_flow.LogShedApiClient.async_verify_auth",
            AsyncMock(return_value=auth_info),
        ),
        patch(
            "custom_components.logshed.config_flow.LogShedApiClient.async_get_system_metrics",
            AsyncMock(return_value=mock_metrics),
        ),
        patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock_reload,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": mock_config_entry.entry_id,
            },
            data=mock_config_entry.data,
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "reauth_confirm"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_API_TOKEN: new_token},
        )
        assert result2["type"] == FlowResultType.ABORT
        assert result2["reason"] == "reauth_successful"
        assert mock_config_entry.data[CONF_API_TOKEN] == new_token
        mock_reload.assert_awaited_once_with(mock_config_entry.entry_id)


async def test_options_flow(hass: HomeAssistant, mock_config_entry: MockConfigEntry) -> None:
    """Test options flow allows changing polling and maintenance settings."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_SCAN_INTERVAL: 15,
            CONF_MAINTENANCE_DURATION: 120,
            CONF_MAINTENANCE_LOG_HANDLING: "drop_errors",
        },
    )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options[CONF_SCAN_INTERVAL] == 15
    assert mock_config_entry.options[CONF_MAINTENANCE_DURATION] == 120
    assert mock_config_entry.options[CONF_MAINTENANCE_LOG_HANDLING] == "drop_errors"


async def test_options_flow_default_fallback(hass: HomeAssistant) -> None:
    """Test options flow when entry has no options and no default duration in data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="fallback-test",
        title="LogShed (Fallback)",
        data={
            CONF_HOST: MOCK_HOST,
            CONF_API_TOKEN: MOCK_TOKEN,
            CONF_VERIFY_SSL: True,
        },
        options={},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_SCAN_INTERVAL: 45,
            CONF_MAINTENANCE_DURATION: 30,
            CONF_MAINTENANCE_LOG_HANDLING: "silence_alerts",
        },
    )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SCAN_INTERVAL] == 45
    assert entry.options[CONF_MAINTENANCE_DURATION] == 30
    assert entry.options[CONF_MAINTENANCE_LOG_HANDLING] == "silence_alerts"
