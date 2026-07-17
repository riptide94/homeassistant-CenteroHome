"""Number platform for Centero cover configuration values."""

from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    LOGGER,
    PRESET_POSITION_MAX,
    PRESET_POSITION_MIN,
    PRESET_POSITION_STEP,
    STATE_INTERMEDIATE,
    STATE_VENT,
    TRAVEL_TIME_MAX,
    TRAVEL_TIME_MIN,
    TRAVEL_TIME_STEP,
)
from .coordinator import CenteroCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Centero cover configuration numbers."""

    coordinator: CenteroCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities: list[NumberEntity] = []

    for device in coordinator.data.values():
        entities.append(CenteroCoverOpenTime(entry, coordinator, device))
        entities.append(CenteroCoverCloseTime(entry, coordinator, device))
        entities.append(CenteroCoverFavoritePosition(entry, coordinator, device))
        entities.append(CenteroCoverVentPosition(entry, coordinator, device))

    async_add_entities(entities)


class CenteroCoverConfigNumber(CoordinatorEntity[CenteroCoordinator], RestoreNumber):
    """Base for a cover configuration number."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: CenteroCoordinator,
        device: dict[str, Any],
        translation_key: str,
    ) -> None:
        """Initialize the number."""

        super().__init__(coordinator)

        self._entry = entry

        self._sid = device["sid"]
        self._adr = device["adr"]

        cover_unique = f"elero_sid{self._sid}_adr{self._adr}"

        self._cover_unique_id = cover_unique
        self._attr_unique_id = f"{cover_unique}_{translation_key}"
        self._attr_translation_key = translation_key

        #
        # Suggest a deterministic entity id; deriving it from the
        # translated name silently degrades to the bare device name
        # when the translation is not available at registration.
        #
        self.entity_id = f"number.{cover_unique}_{translation_key}"

        self._attr_native_value: float | None = None

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
        """Restore the last configured value, if any."""

        await super().async_added_to_hass()

        last_data = await self.async_get_last_number_data()

        if last_data is not None and last_data.native_value is not None:
            self._attr_native_value = last_data.native_value
            self._apply_value(self._attr_native_value)

    def _apply_value(self, value: float | None) -> None:
        """Push the value into the coordinator."""

        raise NotImplementedError

    async def async_set_native_value(self, value: float) -> None:
        """Update the configuration value."""

        LOGGER.debug(
            "Setting %s to %s for SID=%s ADR=%s",
            self._attr_translation_key,
            value,
            self._sid,
            self._adr,
        )

        self._attr_native_value = value
        self._apply_value(value)

        self.async_write_ha_state()


class CenteroTravelTimeNumber(CenteroCoverConfigNumber):
    """Base for a cover travel time configuration number."""

    _attr_native_min_value = TRAVEL_TIME_MIN
    _attr_native_max_value = TRAVEL_TIME_MAX
    _attr_native_step = TRAVEL_TIME_STEP
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS


class CenteroCoverOpenTime(CenteroTravelTimeNumber):
    """Time it takes the cover to move from fully closed to fully open."""

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: CenteroCoordinator,
        device: dict[str, Any],
    ) -> None:
        """Initialize the number."""

        super().__init__(entry, coordinator, device, "open_time")

    def _apply_value(self, value: float | None) -> None:
        """Push the value into the shared travel calculator."""

        self.coordinator.get_travel_calculator(self._adr).set_travel_time_up(value)


class CenteroCoverCloseTime(CenteroTravelTimeNumber):
    """Time it takes the cover to move from fully open to fully closed."""

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: CenteroCoordinator,
        device: dict[str, Any],
    ) -> None:
        """Initialize the number."""

        super().__init__(entry, coordinator, device, "close_time")

    def _apply_value(self, value: float | None) -> None:
        """Push the value into the shared travel calculator."""

        self.coordinator.get_travel_calculator(self._adr).set_travel_time_down(value)


class CenteroPresetPositionNumber(CenteroCoverConfigNumber):
    """Base for a motor preset position configuration number.

    Tells the integration where a motor-programmed preset lies
    (100 = open); it does not program the preset in the motor.
    Unset means the position tracked during the move is kept.
    """

    _attr_native_min_value = PRESET_POSITION_MIN
    _attr_native_max_value = PRESET_POSITION_MAX
    _attr_native_step = PRESET_POSITION_STEP
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: CenteroCoordinator,
        device: dict[str, Any],
        translation_key: str,
        preset_state: str,
    ) -> None:
        """Initialize the number."""

        super().__init__(entry, coordinator, device, translation_key)

        self._preset_state = preset_state

    def _apply_value(self, value: float | None) -> None:
        """Push the value into the coordinator."""

        if value is None:
            return

        self.coordinator.set_preset_position(self._adr, self._preset_state, value)


class CenteroCoverFavoritePosition(CenteroPresetPositionNumber):
    """Position the cover reports when stopped at its favorite preset."""

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: CenteroCoordinator,
        device: dict[str, Any],
    ) -> None:
        """Initialize the number."""

        super().__init__(
            entry,
            coordinator,
            device,
            "favorite_position",
            STATE_INTERMEDIATE,
        )


class CenteroCoverVentPosition(CenteroPresetPositionNumber):
    """Position the cover reports when stopped at its vent preset."""

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: CenteroCoordinator,
        device: dict[str, Any],
    ) -> None:
        """Initialize the number."""

        super().__init__(
            entry,
            coordinator,
            device,
            "vent_position",
            STATE_VENT,
        )
