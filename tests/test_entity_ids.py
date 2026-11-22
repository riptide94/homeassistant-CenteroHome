"""Tests for the generated entity ids of all per-cover entities.

Entity ids derived from translated names silently degrade to the bare
device name (plus _2, _3, ... on collisions) when the translation is
not available at registration time, e.g. right after an integration
update without a full restart. All entities therefore suggest their
entity id explicitly; these tests pin the resulting ids.
"""

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from custom_components.centero.const import STATE_CLOSED

from .common import COVER_UNIQUE_ID, find_entity_id, setup_integration


@pytest.mark.parametrize(
    ("platform", "unique_id"),
    [
        ("cover", COVER_UNIQUE_ID),
        ("number", f"{COVER_UNIQUE_ID}_time_open"),
        ("number", f"{COVER_UNIQUE_ID}_time_close"),
        ("number", f"{COVER_UNIQUE_ID}_position_favorite"),
        ("number", f"{COVER_UNIQUE_ID}_position_vent"),
        ("sensor", f"{COVER_UNIQUE_ID}_state_code"),
        ("sensor", f"{COVER_UNIQUE_ID}_state_translation"),
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


async def test_entity_ids_are_valid_for_hex_addresses(
    hass: HomeAssistant,
    mock_api,
    config_entry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Hex sid/adr bytes with letters (e.g. 0A) still yield valid entity ids.

    The unique id keeps the gateway's spelling; only the suggested
    entity id is lowercased, as entity ids must be.
    """

    mock_api.other_covers["0A"] = STATE_CLOSED

    await setup_integration(hass, config_entry)

    unique_id = "elero_sidS0A_adr0A"

    assert find_entity_id(hass, "cover", unique_id) == "cover.elero_sids0a_adr0a"
    assert (
        find_entity_id(hass, "switch", f"{unique_id}_silent_drive")
        == "switch.elero_sids0a_adr0a_silent_drive"
    )

    assert "sets an invalid entity ID" not in caplog.text


async def test_cover_devices_link_to_gateway(
    hass: HomeAssistant,
    mock_api,
    config_entry,
) -> None:
    """Cover devices are linked to the gateway device via its registry id."""

    await setup_integration(hass, config_entry)

    devices = {
        identifier: device
        for device in dr.async_entries_for_config_entry(
            dr.async_get(hass), config_entry.entry_id
        )
        for _, identifier in device.identifiers
    }

    gateway = devices["aa:bb:cc:dd:ee:ff"]
    cover = devices[COVER_UNIQUE_ID]

    assert gateway.via_device_id is None
    assert cover.via_device_id == gateway.id
