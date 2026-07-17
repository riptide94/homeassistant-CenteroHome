"""Tests for the default icons of the configuration entities.

Icon translations are not part of the entity state; they are served to
the frontend from icons.json, so the parsed icon resources are checked
instead.
"""

from homeassistant.core import HomeAssistant
from homeassistant.helpers.icon import async_get_icons

from custom_components.centero.const import DOMAIN

from .common import setup_integration

EXPECTED_ICONS = {
    "number": {
        "open_time": "mdi:clock-out",
        "close_time": "mdi:clock-in",
        "favorite_position": "mdi:star",
        "vent_position": "mdi:fan",
    },
    "switch": {
        "silent_drive": "mdi:volume-mute",
    },
}


async def test_config_entity_icons(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """Configuration entities declare their default icons."""

    await setup_integration(hass, config_entry)

    icons = await async_get_icons(hass, "entity", integrations=[DOMAIN])

    for platform, keys in EXPECTED_ICONS.items():
        for translation_key, icon in keys.items():
            assert icons[DOMAIN][platform][translation_key]["default"] == icon
