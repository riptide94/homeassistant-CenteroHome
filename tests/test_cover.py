"""Tests for the Centero cover entity, focused on preset position handling."""

from unittest.mock import patch

import pytest

from homeassistant.core import HomeAssistant

from custom_components.centero.const import (
    COMMAND_VENT,
    STATE_CLOSED,
    STATE_INTERMEDIATE,
    STATE_OPEN,
    STATE_OPENING,
    STATE_PARTIAL,
    STATE_VENT,
)

from .common import (
    COVER_UNIQUE_ID,
    FakeClock,
    MOCK_ADR,
    find_entity_id,
    poll,
    set_number,
    setup_integration,
)


@pytest.mark.parametrize("preset_state", [STATE_INTERMEDIATE, STATE_VENT])
async def test_preset_state_defaults_to_half_open(
    hass: HomeAssistant,
    mock_api,
    config_entry,
    preset_state: str,
) -> None:
    """Unconfigured preset states report 50% instead of unknown."""

    mock_api.state = preset_state

    await setup_integration(hass, config_entry)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)
    state = hass.states.get(cover_id)

    assert state.state == "open"
    assert state.attributes["current_position"] == 50


async def test_vent_state_uses_configured_position(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """A configured vent position replaces the 50% default."""

    mock_api.state = STATE_VENT

    await setup_integration(hass, config_entry)

    vent_number = find_entity_id(hass, "number", f"{COVER_UNIQUE_ID}_vent_position")
    await set_number(hass, vent_number, 10)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)
    state = hass.states.get(cover_id)

    assert state.attributes["current_position"] == 10


async def test_favorite_position_zero_still_reads_open(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """A preset configured at 0% reports position 0 but stays 'open'."""

    mock_api.state = STATE_INTERMEDIATE

    await setup_integration(hass, config_entry)

    favorite_number = find_entity_id(
        hass,
        "number",
        f"{COVER_UNIQUE_ID}_favorite_position",
    )
    await set_number(hass, favorite_number, 0)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)
    state = hass.states.get(cover_id)

    assert state.state == "open"
    assert state.attributes["current_position"] == 0


@pytest.mark.parametrize(
    ("gateway_state", "expected_state", "expected_position"),
    [
        (STATE_OPEN, "open", 100),
        (STATE_CLOSED, "closed", 0),
        (STATE_PARTIAL, "open", 50),
    ],
)
async def test_discrete_position_mapping_unchanged(
    hass: HomeAssistant,
    mock_api,
    config_entry,
    gateway_state: str,
    expected_state: str,
    expected_position: int,
) -> None:
    """Endpoint and partial states keep their existing mapping."""

    mock_api.state = gateway_state

    await setup_integration(hass, config_entry)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)
    state = hass.states.get(cover_id)

    assert state.state == expected_state
    assert state.attributes["current_position"] == expected_position


async def test_vent_service_tracks_position_through_transit(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """The position estimate keeps tracking while driving to a preset.

    Scenario from the plan review: the cover position is known, the
    vent position is not configured. The vent command must not
    invalidate the estimate; the gateway-reported movement drives the
    interpolation, and the frozen estimate survives the arrival.
    """

    mock_api.state = STATE_CLOSED

    await setup_integration(hass, config_entry)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)

    await set_number(
        hass,
        find_entity_id(hass, "number", f"{COVER_UNIQUE_ID}_open_time"),
        10,
    )
    await set_number(
        hass,
        find_entity_id(hass, "number", f"{COVER_UNIQUE_ID}_close_time"),
        10,
    )

    clock = FakeClock()

    with patch("custom_components.centero.travel_calculator.time", clock):
        await hass.services.async_call(
            "centero",
            "vent",
            {"entity_id": cover_id},
            blocking=True,
        )
        await hass.async_block_till_done()

        assert (MOCK_ADR, COMMAND_VENT) in mock_api.sent_commands

        #
        # The estimate is not invalidated by the command.
        #
        state = hass.states.get(cover_id)
        assert state.attributes["current_position"] == 0

        #
        # The gateway reports the movement it decided on.
        #
        mock_api.state = STATE_OPENING
        await poll(hass, config_entry)

        clock.now += 3

        #
        # Arrival at the vent preset freezes the tracked estimate:
        # 3s of a 10s open time from position 0 -> 30%.
        #
        mock_api.state = STATE_VENT
        await poll(hass, config_entry)

        state = hass.states.get(cover_id)
        assert state.state == "open"
        assert state.attributes["current_position"] == 30


async def test_configured_position_overrides_tracked_estimate(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """On arrival, a configured preset position beats the tracked estimate."""

    mock_api.state = STATE_CLOSED

    await setup_integration(hass, config_entry)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)

    await set_number(
        hass,
        find_entity_id(hass, "number", f"{COVER_UNIQUE_ID}_open_time"),
        10,
    )
    await set_number(
        hass,
        find_entity_id(hass, "number", f"{COVER_UNIQUE_ID}_close_time"),
        10,
    )
    await set_number(
        hass,
        find_entity_id(hass, "number", f"{COVER_UNIQUE_ID}_vent_position"),
        60,
    )

    clock = FakeClock()

    with patch("custom_components.centero.travel_calculator.time", clock):
        mock_api.state = STATE_OPENING
        await poll(hass, config_entry)

        clock.now += 3

        mock_api.state = STATE_VENT
        await poll(hass, config_entry)

        state = hass.states.get(cover_id)
        assert state.attributes["current_position"] == 60
