"""Number platform for Centero cover travel times."""

from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    LOGGER,
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
    """Set up Centero cover travel time numbers."""

    coordinator: CenteroCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities: list[NumberEntity] = []

    for device in coordinator.data.values():
        entities.append(CenteroCoverOpenTime(entry, coordinator, device))
        entities.append(CenteroCoverCloseTime(entry, coordinator, device))

    async_add_entities(entities)


class CenteroTravelTimeNumber(CoordinatorEntity[CenteroCoordinator], RestoreNumber):
    """Base for a cover travel time configuration number."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = TRAVEL_TIME_MIN
    _attr_native_max_value = TRAVEL_TIME_MAX
    _attr_native_step = TRAVEL_TIME_STEP
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS

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
            self._apply_travel_time(self._attr_native_value)

    def _apply_travel_time(self, value: float | None) -> None:
        """Push the value into the shared travel calculator."""

        raise NotImplementedError

    async def async_set_native_value(self, value: float) -> None:
        """Update the travel time."""

        LOGGER.debug(
            "Setting %s to %s seconds for SID=%s ADR=%s",
            self._attr_translation_key,
            value,
            self._sid,
            self._adr,
        )

        self._attr_native_value = value
        self._apply_travel_time(value)

        self.async_write_ha_state()


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

    def _apply_travel_time(self, value: float | None) -> None:
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

    def _apply_travel_time(self, value: float | None) -> None:
        """Push the value into the shared travel calculator."""

        self.coordinator.get_travel_calculator(self._adr).set_travel_time_down(value)
