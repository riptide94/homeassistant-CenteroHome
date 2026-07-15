"""Switch platform for Centero silent-drive mode."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LOGGER
from .coordinator import CenteroCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Centero silent-drive switches."""

    coordinator: CenteroCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities = [
        CenteroSilentDriveSwitch(entry, coordinator, device)
        for device in coordinator.data.values()
    ]

    async_add_entities(entities)


class CenteroSilentDriveSwitch(
    CoordinatorEntity[CenteroCoordinator], SwitchEntity, RestoreEntity
):
    """Switch enabling silent (quiet/slow) drive commands for a cover."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "silent_drive"

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: CenteroCoordinator,
        device: dict[str, Any],
    ) -> None:
        """Initialize the switch."""

        super().__init__(coordinator)

        self._entry = entry

        self._sid = device["sid"]
        self._adr = device["adr"]

        cover_unique = f"elero_sid{self._sid}_adr{self._adr}"

        self._cover_unique_id = cover_unique
        self._attr_unique_id = f"{cover_unique}_silent_drive"

        self._attr_is_on = False

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information, matching the cover's device."""

        gateway_info = self.hass.data[DOMAIN][self._entry.entry_id]["gateway_info"]

        return DeviceInfo(
            identifiers={(DOMAIN, self._cover_unique_id)},
            manufacturer="Elero",
            model="Centero controlled cover",
            via_device=(
                DOMAIN,
                gateway_info.get("mac", self._entry.entry_id),
            ),
        )

    async def async_added_to_hass(self) -> None:
        """Restore the last known state and push it into the coordinator."""

        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()

        if last_state is not None:
            self._attr_is_on = last_state.state == "on"

        LOGGER.debug(
            "Restored silent-drive state for SID=%s ADR=%s: %s",
            self._sid,
            self._adr,
            self._attr_is_on,
        )

        self.coordinator.set_silent_drive(self._adr, self._attr_is_on)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on silent drive."""

        LOGGER.debug(
            "Enabling silent drive for SID=%s ADR=%s",
            self._sid,
            self._adr,
        )

        self._attr_is_on = True
        self.coordinator.set_silent_drive(self._adr, True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off silent drive."""

        LOGGER.debug(
            "Disabling silent drive for SID=%s ADR=%s",
            self._sid,
            self._adr,
        )

        self._attr_is_on = False
        self.coordinator.set_silent_drive(self._adr, False)
        self.async_write_ha_state()
