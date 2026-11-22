"""Tests for the Centero cover state diagnostic sensors."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.centero.const import STATE_OPEN

from .common import COVER_UNIQUE_ID, find_entity_id, setup_integration


async def test_state_sensors_disabled_by_default(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """The diagnostic sensors are registered but not enabled by default."""

    await setup_integration(hass, config_entry)

    registry = er.async_get(hass)

    for key in ("state_code", "state_translation"):
        entity_id = find_entity_id(hass, "sensor", f"{COVER_UNIQUE_ID}_{key}")

        entry = registry.entities[entity_id]
        assert entry.disabled_by == er.RegistryEntryDisabler.INTEGRATION

        assert hass.states.get(entity_id) is None


async def test_state_sensors_reflect_gateway_state(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """Once enabled, the sensors report the raw code and its translation."""

    mock_api.state = STATE_OPEN

    await setup_integration(hass, config_entry)

    registry = er.async_get(hass)

    code_id = find_entity_id(hass, "sensor", f"{COVER_UNIQUE_ID}_state_code")
    translation_id = find_entity_id(
        hass, "sensor", f"{COVER_UNIQUE_ID}_state_translation"
    )

    for entity_id in (code_id, translation_id):
        registry.async_update_entity(entity_id, disabled_by=None)

    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(code_id).state == STATE_OPEN
    assert hass.states.get(translation_id).state == "open"
