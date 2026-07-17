"""Tests for the Centero preset position number entities."""

from homeassistant.core import HomeAssistant

from custom_components.centero.const import DOMAIN, STATE_INTERMEDIATE

from .common import (
    COVER_UNIQUE_ID,
    MOCK_ADR,
    find_entity_id,
    set_number,
    setup_integration,
)


async def test_preset_position_numbers_created(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """Both preset position numbers exist per cover and start unset."""

    await setup_integration(hass, config_entry)

    for key in ("favorite_position", "vent_position"):
        entity_id = find_entity_id(hass, "number", f"{COVER_UNIQUE_ID}_{key}")

        #
        # The entity id must identify device and entity, and must not
        # depend on the translated name being available.
        #
        assert entity_id == f"number.{COVER_UNIQUE_ID}_{key}"

        state = hass.states.get(entity_id)

        assert state.state == "unknown"
        assert state.attributes["min"] == 0
        assert state.attributes["max"] == 100
        assert state.attributes["unit_of_measurement"] == "%"


async def test_set_value_applies_immediately(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """Setting the number updates a cover sitting at the preset right away."""

    mock_api.state = STATE_INTERMEDIATE

    await setup_integration(hass, config_entry)

    favorite_number = find_entity_id(
        hass,
        "number",
        f"{COVER_UNIQUE_ID}_favorite_position",
    )
    await set_number(hass, favorite_number, 25)

    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

    assert coordinator.configured_preset_position(MOCK_ADR, STATE_INTERMEDIATE) == 25

    #
    # No poll has run since the service call; the cover position must
    # have been updated by the immediate-apply path.
    #
    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)
    state = hass.states.get(cover_id)

    assert state.attributes["current_position"] == 25


async def test_value_restored_across_reload(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """A configured value survives a reload and applies before the next poll.

    On startup the coordinator's first refresh runs before the number
    entities restore their values, so a cover sitting at its preset
    briefly resolves to the 50% fallback; the restore must correct it
    without waiting for the next poll.
    """

    mock_api.state = STATE_INTERMEDIATE

    await setup_integration(hass, config_entry)

    favorite_number = find_entity_id(
        hass,
        "number",
        f"{COVER_UNIQUE_ID}_favorite_position",
    )
    await set_number(hass, favorite_number, 25)

    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(favorite_number)
    assert float(state.state) == 25

    cover_id = find_entity_id(hass, "cover", COVER_UNIQUE_ID)
    state = hass.states.get(cover_id)

    assert state.attributes["current_position"] == 25
