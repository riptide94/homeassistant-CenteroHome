"""Tests for the RefreshSC radio queries that correct stale gateway states."""

from unittest.mock import patch

from homeassistant.core import HomeAssistant

from custom_components.centero.const import (
    DOMAIN,
    FAST_POLL_INTERVAL,
    MOVEMENT_TIMEOUT_DEFAULT_SECONDS,
    MOVEMENT_TIMEOUT_MARGIN_SECONDS,
    POLL_INTERVAL,
    STATE_CLOSED,
    STATE_CLOSING,
    STATE_OPEN,
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

COORDINATOR_TIME = "custom_components.centero.coordinator.time"


async def _close_cover(hass: HomeAssistant, cover_id: str) -> None:
    """Call the cover.close_cover service."""

    await hass.services.async_call(
        "cover",
        "close_cover",
        {"entity_id": cover_id},
        blocking=True,
    )
    await hass.async_block_till_done()


async def _start_stuck_close(hass: HomeAssistant, mock_api, cover_id: str) -> None:
    """Close the cover via HA; the gateway then misses the end of travel.

    The gateway caches its own command's moving state right away and
    never learns that the motor reached the end stop - only a RefreshSC
    radio query reveals the real state.
    """

    mock_api.state = STATE_CLOSING
    mock_api.radio_state = STATE_CLOSED

    await _close_cover(hass, cover_id)

    assert hass.states.get(cover_id).state == "closing"


async def test_stuck_ha_movement_is_refreshed_after_default_timeout(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """A stuck HA-commanded move is radio-queried once it is overdue."""

    mock_api.state = STATE_OPEN

    await setup_integration(hass, config_entry)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)

    clock = FakeClock()

    with patch(COORDINATOR_TIME, clock):
        await _start_stuck_close(hass, mock_api, cover_id)

        #
        # Within the expected duration the radio is kept clear for the
        # HA-commanded movement.
        #
        clock.now += MOVEMENT_TIMEOUT_DEFAULT_SECONDS - 1
        await poll(hass, config_entry)

        assert mock_api.refreshed == []
        assert hass.states.get(cover_id).state == "closing"

        #
        # Overdue: the cover is radio-queried, which also fixes the
        # gateway's cache.
        #
        clock.now += 2
        await poll(hass, config_entry)

        assert mock_api.refreshed == [MOCK_ADR]
        assert mock_api.state == STATE_CLOSED
        assert hass.states.get(cover_id).state == "closed"

        #
        # The correction sticks on the following plain GetStates polls.
        #
        await poll(hass, config_entry)

        assert hass.states.get(cover_id).state == "closed"


async def test_stuck_ha_movement_timeout_uses_drive_time(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """With a configured drive time, the re-check comes after drive time + margin."""

    mock_api.state = STATE_OPEN

    await setup_integration(hass, config_entry)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)

    await set_number(
        hass,
        find_entity_id(hass, "number", f"{COVER_UNIQUE_ID}_time_close"),
        20,
    )

    clock = FakeClock()

    with patch(COORDINATOR_TIME, clock):
        await _start_stuck_close(hass, mock_api, cover_id)

        clock.now += 20 + MOVEMENT_TIMEOUT_MARGIN_SECONDS - 1
        await poll(hass, config_entry)

        assert mock_api.refreshed == []

        clock.now += 2
        await poll(hass, config_entry)

        assert mock_api.refreshed == [MOCK_ADR]
        assert hass.states.get(cover_id).state == "closed"


async def test_new_command_restarts_movement_timeout(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """Re-issuing a command gives the movement a fresh expected duration."""

    mock_api.state = STATE_OPEN

    await setup_integration(hass, config_entry)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)

    clock = FakeClock()

    with patch(COORDINATOR_TIME, clock):
        await _start_stuck_close(hass, mock_api, cover_id)

        clock.now += MOVEMENT_TIMEOUT_DEFAULT_SECONDS - 1
        await _close_cover(hass, cover_id)

        clock.now += 2
        await poll(hass, config_entry)

        assert mock_api.refreshed == []
        assert hass.states.get(cover_id).state == "closing"


async def test_stuck_moving_state_at_startup_is_refreshed(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """A moving state already cached at startup is not HA's; query it right away."""

    mock_api.state = STATE_CLOSING
    mock_api.radio_state = STATE_CLOSED

    await setup_integration(hass, config_entry)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)

    await poll(hass, config_entry)

    assert mock_api.refreshed == [MOCK_ADR]
    assert hass.states.get(cover_id).state == "closed"


async def test_initial_sweep_queries_every_cover_once(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """After startup each cover is queried once, at the fast poll interval."""

    mock_api.other_covers = {"05": STATE_CLOSED, "01": STATE_OPEN}

    await setup_integration(hass, config_entry)

    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

    assert coordinator.update_interval == FAST_POLL_INTERVAL

    for _ in range(3):
        await poll(hass, config_entry)

    assert mock_api.refreshed == ["01", MOCK_ADR, "05"]
    assert coordinator.update_interval == POLL_INTERVAL


async def test_initial_sweep_corrects_stale_idle_state(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """A cover moved while HA was down is corrected by the initial sweep."""

    #
    # Closed when the gateway last knew; since moved to a partial
    # position via a wall switch.
    #
    mock_api.state = STATE_CLOSED
    mock_api.radio_state = STATE_PARTIAL

    await setup_integration(hass, config_entry)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)

    assert hass.states.get(cover_id).state == "closed"

    await poll(hass, config_entry)

    assert mock_api.refreshed == [MOCK_ADR]
    assert mock_api.state == STATE_PARTIAL
    assert hass.states.get(cover_id).state == "open"


async def test_initial_sweep_waits_for_ha_movement(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """The initial sweep keeps the radio clear for HA-commanded movement."""

    mock_api.state = STATE_OPEN

    await setup_integration(hass, config_entry)

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)

    mock_api.state = STATE_CLOSING

    await _close_cover(hass, cover_id)

    assert mock_api.refreshed == []

    #
    # The movement ends; the poll that observes this was still planned
    # during the movement, the next one resumes the sweep.
    #
    mock_api.state = STATE_CLOSED

    await poll(hass, config_entry)

    assert mock_api.refreshed == []

    await poll(hass, config_entry)

    assert mock_api.refreshed == [MOCK_ADR]
