"""Tests for the Centero cover set-position feature."""

from datetime import timedelta
from unittest.mock import patch

import pytest

from homeassistant.components.cover import CoverEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
import homeassistant.util.dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.centero.const import (
    COMMAND_DOWN,
    COMMAND_STOP,
    COMMAND_UP,
    COMMAND_UP_SILENT,
    STATE_CLOSED,
    STATE_CLOSING,
    STATE_NO_INFO,
    STATE_OPEN,
    STATE_OPENING,
    STATE_PARTIAL,
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


async def _configure_times(
    hass: HomeAssistant,
    time_open: float = 10,
    time_close: float = 20,
) -> None:
    """Configure both drive times (asymmetric by default)."""

    await set_number(
        hass,
        find_entity_id(hass, "number", f"{COVER_UNIQUE_ID}_time_open"),
        time_open,
    )
    await set_number(
        hass,
        find_entity_id(hass, "number", f"{COVER_UNIQUE_ID}_time_close"),
        time_close,
    )


async def _set_position(hass: HomeAssistant, cover_id: str, position: int) -> None:
    """Call the cover.set_cover_position service."""

    await hass.services.async_call(
        "cover",
        "set_cover_position",
        {"entity_id": cover_id, "position": position},
        blocking=True,
    )
    await hass.async_block_till_done()


async def _fire_in(hass: HomeAssistant, seconds: float) -> None:
    """Fire scheduled timers due within the given wall-clock delay."""

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done()


async def test_set_position_not_supported_without_travel_times(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """SET_POSITION is not advertised until both drive times are set."""

    await setup_integration(hass, config_entry)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)

    features = hass.states.get(cover_id).attributes["supported_features"]
    assert not features & CoverEntityFeature.SET_POSITION

    await set_number(
        hass,
        find_entity_id(hass, "number", f"{COVER_UNIQUE_ID}_time_open"),
        10,
    )

    features = hass.states.get(cover_id).attributes["supported_features"]
    assert not features & CoverEntityFeature.SET_POSITION


async def test_set_position_supported_once_times_configured(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """SET_POSITION appears right after both drive times are set, no poll."""

    await setup_integration(hass, config_entry)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)

    await _configure_times(hass)

    features = hass.states.get(cover_id).attributes["supported_features"]
    assert features & CoverEntityFeature.SET_POSITION


async def test_set_position_service_rejected_when_unconfigured(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """The service is rejected while drive times are not configured."""

    await setup_integration(hass, config_entry)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)

    with pytest.raises(HomeAssistantError):
        await _set_position(hass, cover_id, 60)

    assert mock_api.sent_commands == []


async def test_set_position_opens_and_stops_at_target(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """A timed stop halts the cover at the requested position."""

    mock_api.state = STATE_CLOSED

    await setup_integration(hass, config_entry)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)

    await _configure_times(hass, time_open=10, time_close=20)

    clock = FakeClock()

    with patch("custom_components.centero.travel_calculator.time", clock):
        #
        # The gateway updates its cached state immediately for its own
        # commands, so it reports the movement as soon as we send it.
        #
        mock_api.state = STATE_OPENING

        await _set_position(hass, cover_id, 60)

        assert (MOCK_ADR, COMMAND_UP) in mock_api.sent_commands
        assert (MOCK_ADR, COMMAND_STOP) not in mock_api.sent_commands
        assert hass.states.get(cover_id).state == "opening"

        #
        # 60% of a 10s open time from position 0 -> stop after 6s.
        #
        clock.now += 6
        await _fire_in(hass, 6.1)

        assert (MOCK_ADR, COMMAND_STOP) in mock_api.sent_commands

        state = hass.states.get(cover_id)
        assert state.attributes["current_position"] == 60

        #
        # The gateway confirms the stop; the frozen estimate survives.
        #
        mock_api.state = STATE_PARTIAL
        await poll(hass, config_entry)

        state = hass.states.get(cover_id)
        assert state.state == "open"
        assert state.attributes["current_position"] == 60


async def test_set_position_closing_uses_down_travel_time(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """Closing travel uses the down travel time, not the up time."""

    mock_api.state = STATE_OPEN

    await setup_integration(hass, config_entry)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)

    await _configure_times(hass, time_open=10, time_close=20)

    clock = FakeClock()

    with patch("custom_components.centero.travel_calculator.time", clock):
        mock_api.state = STATE_CLOSING

        await _set_position(hass, cover_id, 40)

        assert (MOCK_ADR, COMMAND_DOWN) in mock_api.sent_commands

        #
        # 60% of a 20s close time from position 100 -> stop after 12s.
        #
        clock.now += 12
        await _fire_in(hass, 12.1)

        assert (MOCK_ADR, COMMAND_STOP) in mock_api.sent_commands
        assert hass.states.get(cover_id).attributes["current_position"] == 40


async def test_set_position_100_delegates_to_open(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """Target 100 drives fully open without a timed stop."""

    mock_api.state = STATE_PARTIAL

    await setup_integration(hass, config_entry)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)

    await _configure_times(hass)

    clock = FakeClock()

    with patch("custom_components.centero.travel_calculator.time", clock):
        mock_api.state = STATE_OPENING

        await _set_position(hass, cover_id, 100)

        assert (MOCK_ADR, COMMAND_UP) in mock_api.sent_commands

        clock.now += 400
        await _fire_in(hass, 400)

        assert (MOCK_ADR, COMMAND_STOP) not in mock_api.sent_commands

        mock_api.state = STATE_OPEN
        await poll(hass, config_entry)

        assert hass.states.get(cover_id).attributes["current_position"] == 100


async def test_set_position_0_delegates_to_close(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """Target 0 drives fully closed without a timed stop."""

    mock_api.state = STATE_PARTIAL

    await setup_integration(hass, config_entry)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)

    await _configure_times(hass)

    clock = FakeClock()

    with patch("custom_components.centero.travel_calculator.time", clock):
        mock_api.state = STATE_CLOSING

        await _set_position(hass, cover_id, 0)

        assert (MOCK_ADR, COMMAND_DOWN) in mock_api.sent_commands

        clock.now += 400
        await _fire_in(hass, 400)

        assert (MOCK_ADR, COMMAND_STOP) not in mock_api.sent_commands

        mock_api.state = STATE_CLOSED
        await poll(hass, config_entry)

        assert hass.states.get(cover_id).attributes["current_position"] == 0


async def test_set_position_within_threshold_is_noop(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """A target within the minimum delta of the estimate sends nothing."""

    mock_api.state = STATE_PARTIAL

    await setup_integration(hass, config_entry)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)

    await _configure_times(hass)

    await _set_position(hass, cover_id, 50)

    assert mock_api.sent_commands == []
    assert hass.states.get(cover_id).attributes["current_position"] == 50


async def test_manual_stop_cancels_position_timer(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """A manual stop mid-run cancels the pending timed stop."""

    mock_api.state = STATE_CLOSED

    await setup_integration(hass, config_entry)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)

    await _configure_times(hass, time_open=10, time_close=20)

    clock = FakeClock()

    with patch("custom_components.centero.travel_calculator.time", clock):
        mock_api.state = STATE_OPENING

        await _set_position(hass, cover_id, 60)

        clock.now += 3

        await hass.services.async_call(
            "cover",
            "stop_cover",
            {"entity_id": cover_id},
            blocking=True,
        )
        await hass.async_block_till_done()

        assert mock_api.sent_commands.count((MOCK_ADR, COMMAND_STOP)) == 1
        assert hass.states.get(cover_id).attributes["current_position"] == 30

        clock.now += 10
        await _fire_in(hass, 10)

        assert mock_api.sent_commands.count((MOCK_ADR, COMMAND_STOP)) == 1
        assert hass.states.get(cover_id).attributes["current_position"] == 30


async def test_manual_open_cancels_position_timer(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """A manual open mid-run cancels the pending timed stop."""

    mock_api.state = STATE_CLOSED

    await setup_integration(hass, config_entry)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)

    await _configure_times(hass, time_open=10, time_close=20)

    clock = FakeClock()

    with patch("custom_components.centero.travel_calculator.time", clock):
        mock_api.state = STATE_OPENING

        await _set_position(hass, cover_id, 60)

        await hass.services.async_call(
            "cover",
            "open_cover",
            {"entity_id": cover_id},
            blocking=True,
        )
        await hass.async_block_till_done()

        clock.now += 10
        await _fire_in(hass, 10)

        assert (MOCK_ADR, COMMAND_STOP) not in mock_api.sent_commands

        await poll(hass, config_entry)

        assert hass.states.get(cover_id).attributes["current_position"] == 100


async def test_new_set_position_supersedes_pending_timer(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """A second set_position replaces the pending timed stop."""

    mock_api.state = STATE_CLOSED

    await setup_integration(hass, config_entry)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)

    await _configure_times(hass, time_open=10, time_close=20)

    clock = FakeClock()

    with patch("custom_components.centero.travel_calculator.time", clock):
        mock_api.state = STATE_OPENING

        await _set_position(hass, cover_id, 30)
        await _set_position(hass, cover_id, 80)

        assert mock_api.sent_commands.count((MOCK_ADR, COMMAND_UP)) == 2

        #
        # Only the second target's stop fires: 80% of 10s -> 8s.
        #
        clock.now += 8
        await _fire_in(hass, 8.1)

        assert mock_api.sent_commands.count((MOCK_ADR, COMMAND_STOP)) == 1
        assert hass.states.get(cover_id).attributes["current_position"] == 80


async def test_external_state_change_cancels_position_timer(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """A gateway-reported arrival mid-run cancels the pending stop."""

    mock_api.state = STATE_CLOSED

    await setup_integration(hass, config_entry)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)

    await _configure_times(hass, time_open=10, time_close=20)

    clock = FakeClock()

    with patch("custom_components.centero.travel_calculator.time", clock):
        mock_api.state = STATE_OPENING

        await _set_position(hass, cover_id, 60)

        #
        # The cover reaches the top end stop before the timer fires.
        #
        mock_api.state = STATE_OPEN
        await poll(hass, config_entry)

        assert hass.states.get(cover_id).attributes["current_position"] == 100

        clock.now += 10
        await _fire_in(hass, 10)

        assert (MOCK_ADR, COMMAND_STOP) not in mock_api.sent_commands


async def test_external_reversal_cancels_position_timer(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """An externally-commanded reversal mid-run cancels the pending stop."""

    mock_api.state = STATE_CLOSED

    await setup_integration(hass, config_entry)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)

    await _configure_times(hass, time_open=10, time_close=20)

    clock = FakeClock()

    with patch("custom_components.centero.travel_calculator.time", clock):
        mock_api.state = STATE_OPENING

        await _set_position(hass, cover_id, 60)

        clock.now += 3

        #
        # The physical remote reverses the cover mid-run.
        #
        mock_api.state = STATE_CLOSING
        await poll(hass, config_entry)

        clock.now += 10
        await _fire_in(hass, 10)

        assert (MOCK_ADR, COMMAND_STOP) not in mock_api.sent_commands

        #
        # The estimate tracks the reversed movement: from 30% down
        # for 2s of a 20s close time -> 20%.
        #
        clock.now += 2
        await poll(hass, config_entry)

        assert hass.states.get(cover_id).attributes["current_position"] < 30


async def test_stale_moving_report_after_timed_stop_keeps_position(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """Stale moving reports right after the timed stop are ignored."""

    mock_api.state = STATE_CLOSED

    await setup_integration(hass, config_entry)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)

    await _configure_times(hass, time_open=10, time_close=20)

    clock = FakeClock()

    with patch("custom_components.centero.travel_calculator.time", clock):
        mock_api.state = STATE_OPENING

        await _set_position(hass, cover_id, 60)

        clock.now += 6
        await _fire_in(hass, 6.1)

        assert mock_api.sent_commands.count((MOCK_ADR, COMMAND_STOP)) == 1

        #
        # The gateway keeps reporting the old moving state for a
        # moment; the stop grace keeps the frozen estimate.
        #
        await poll(hass, config_entry)

        assert hass.states.get(cover_id).attributes["current_position"] == 60


async def test_set_position_with_unknown_position_raises(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """Without a known current position the service fails visibly."""

    mock_api.state = STATE_NO_INFO

    await setup_integration(hass, config_entry)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)

    await _configure_times(hass)

    with pytest.raises(HomeAssistantError):
        await _set_position(hass, cover_id, 60)

    assert mock_api.sent_commands == []


async def test_set_position_uses_silent_commands(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """Silent drive uses the silent variants of the drive commands."""

    mock_api.state = STATE_CLOSED

    await setup_integration(hass, config_entry)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)

    await _configure_times(hass, time_open=10, time_close=20)

    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": find_entity_id(hass, "switch", f"{COVER_UNIQUE_ID}_silent_drive")},
        blocking=True,
    )
    await hass.async_block_till_done()

    clock = FakeClock()

    with patch("custom_components.centero.travel_calculator.time", clock):
        mock_api.state = STATE_OPENING

        await _set_position(hass, cover_id, 60)

        assert (MOCK_ADR, COMMAND_UP_SILENT) in mock_api.sent_commands
        assert (MOCK_ADR, COMMAND_UP) not in mock_api.sent_commands

        clock.now += 6
        await _fire_in(hass, 6.1)

        assert (MOCK_ADR, COMMAND_STOP) in mock_api.sent_commands


async def test_unload_cancels_position_timer(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """Unloading the entry mid-run cancels the pending timed stop."""

    mock_api.state = STATE_CLOSED

    await setup_integration(hass, config_entry)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)

    await _configure_times(hass, time_open=10, time_close=20)

    clock = FakeClock()

    with patch("custom_components.centero.travel_calculator.time", clock):
        mock_api.state = STATE_OPENING

        await _set_position(hass, cover_id, 60)

        assert await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()

        clock.now += 10
        await _fire_in(hass, 10)

        assert (MOCK_ADR, COMMAND_STOP) not in mock_api.sent_commands
