"""Tests for the Centero config flow."""

from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.centero.api import CenteroApiError
from custom_components.centero.const import DOMAIN

GATEWAY_INFO = {"XC_SUC": {"name": "Test Gateway", "mac": "aa:bb:cc:dd:ee:ff"}}


async def test_user_flow_recovers_from_connection_error(
    hass: HomeAssistant,
    mock_api,
) -> None:
    """A failed connection shows an error; a retry creates the entry."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(
        "custom_components.centero.config_flow.CenteroAPI.get_info",
        AsyncMock(side_effect=CenteroApiError("unreachable")),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.0.2.10"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    with patch(
        "custom_components.centero.config_flow.CenteroAPI.get_info",
        AsyncMock(return_value=GATEWAY_INFO),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.0.2.10"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Test Gateway"
    assert result["data"] == {CONF_HOST: "192.0.2.10"}
    assert result["result"].unique_id == "192.0.2.10"


async def test_user_flow_aborts_for_configured_host(hass: HomeAssistant) -> None:
    """A gateway host can only be configured once."""

    MockConfigEntry(
        domain=DOMAIN,
        unique_id="127.0.0.1",
        data={CONF_HOST: "127.0.0.1"},
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
