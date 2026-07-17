"""Tests for the generated entity ids of all per-cover entities.

Entity ids derived from translated names silently degrade to the bare
device name (plus _2, _3, ... on collisions) when the translation is
not available at registration time, e.g. right after an integration
update without a full restart. All entities therefore suggest their
entity id explicitly; these tests pin the resulting ids.
"""

import pytest

from homeassistant.core import HomeAssistant

from .common import COVER_UNIQUE_ID, find_entity_id, setup_integration


@pytest.mark.parametrize(
    ("platform", "unique_id"),
    [
        ("cover", COVER_UNIQUE_ID),
        ("number", f"{COVER_UNIQUE_ID}_open_time"),
        ("number", f"{COVER_UNIQUE_ID}_close_time"),
        ("number", f"{COVER_UNIQUE_ID}_favorite_position"),
        ("number", f"{COVER_UNIQUE_ID}_vent_position"),
        ("switch", f"{COVER_UNIQUE_ID}_silent_drive"),
    ],
)
async def test_entity_ids_match_unique_ids(
    hass: HomeAssistant,
    mock_api,
    config_entry,
    platform: str,
    unique_id: str,
) -> None:
    """Every per-cover entity id mirrors its unique id."""

    await setup_integration(hass, config_entry)

    assert find_entity_id(hass, platform, unique_id) == f"{platform}.{unique_id}"
