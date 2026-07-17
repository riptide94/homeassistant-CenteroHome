"""Cover platform for Centero."""

from typing import Any

from homeassistant.components.cover import CoverEntity, CoverEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CLOSING_STATES,
    COMMAND_DOWN,
    COMMAND_DOWN_SILENT,
    COMMAND_FAVORITE,
    COMMAND_STOP,
    COMMAND_UP,
    COMMAND_UP_SILENT,
    COMMAND_VENT,
    DOMAIN,
    ERROR_STATES,
    LOGGER,
    MOVING_STATES,
    OPENING_STATES,
    PRESET_POSITION_DEFAULT,
    PRESET_STATES,
    STATE_BOTTOM_INTERMEDIATE,
    STATE_CLOSED,
    STATE_CLOSING,
    STATE_NAMES,
    STATE_OPEN,
    STATE_OPENING,
    STATE_PARTIAL,
    STATE_TOP_TILT,
    KNOWN_STATES,
)
from .coordinator import CenteroCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Centero covers."""

    coordinator: CenteroCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities = [
        CenteroCover(entry, coordinator, device) for device in coordinator.data.values()
    ]

    platform = entity_platform.async_get_current_platform()

    platform.async_register_entity_service(
        "vent",
        {},
        "async_vent_cover",
    )

    platform.async_register_entity_service(
        "favorite",
        {},
        "async_favorite_cover",
    )

    async_add_entities(entities)


class CenteroCover(CoordinatorEntity[CenteroCoordinator], CoverEntity):
    """Representation of a Centero cover."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: CenteroCoordinator,
        device: dict[str, Any],
    ) -> None:
        """Initialize the cover."""

        super().__init__(coordinator)

        self._entry = entry

        self._sid = device["sid"]
        self._adr = device["adr"]

        unique = f"elero_sid{self._sid}_adr{self._adr}"

        self._attr_unique_id = unique
        self._attr_translation_key = "cover"

        self._attr_name = f"Elero SID{self._sid} ADR{self._adr}"

        #
        # Suggest a deterministic entity id; deriving it from the name
        # would duplicate the device name (which is the same as the
        # entity name) into cover.elero_sid01_adr03_elero_sid01_adr03.
        #
        self.entity_id = f"cover.{unique}"

        self._attr_supported_features = (
            CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""

        gateway_info = self.hass.data[DOMAIN][self._entry.entry_id]["gateway_info"]

        return DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            manufacturer="Elero",
            model="Centero controlled cover",
            name=self._attr_name,
            via_device=(
                DOMAIN,
                gateway_info.get("mac", self._entry.entry_id),
            ),
        )

    @property
    def _device_data(self) -> dict[str, Any] | None:
        """Return coordinator data for this cover."""

        return self.coordinator.data.get(self._adr)

    @property
    def available(self) -> bool:
        """Return availability."""

        return super().available and self._device_data is not None

    @property
    def is_closed(self) -> bool | None:
        """Return whether the cover is closed."""

        device = self._device_data

        if device is None:
            return None

        state = device["state"]

        if state in (STATE_CLOSED, STATE_BOTTOM_INTERMEDIATE):
            return True

        if (
            state in (STATE_OPEN, STATE_PARTIAL, STATE_TOP_TILT)
            or state in MOVING_STATES
            or state in PRESET_STATES
        ):
            return False

        return None

    @property
    def is_opening(self) -> bool:
        """Return whether the cover is opening."""

        device = self._device_data

        return device is not None and device["state"] in OPENING_STATES

    @property
    def current_cover_position(self):
        """Return the current position of the cover."""

        calc = self.coordinator.get_travel_calculator(self._adr)

        if calc.is_configured:
            position = calc.current_position()

            if position is not None:
                return round(position)

        device = self._device_data

        if device is None:
            return None

        state = device["state"]

        if state in (STATE_OPEN, STATE_TOP_TILT):
            return 100

        if state in (STATE_CLOSED, STATE_BOTTOM_INTERMEDIATE):
            return 0

        if state in PRESET_STATES:
            configured = self.coordinator.configured_preset_position(
                self._adr,
                state,
            )

            if configured is not None:
                return configured

            return PRESET_POSITION_DEFAULT

        if state == STATE_PARTIAL:
            return 50

        return None

    @property
    def is_closing(self) -> bool:
        """Return whether the cover is closing."""

        device = self._device_data

        return device is not None and device["state"] in CLOSING_STATES

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""

        device = self._device_data

        if device is None:
            return {
                "sid": self._sid,
                "adr": self._adr,
                "available_from_gateway": False,
            }

        state = device["state"]

        calc = self.coordinator.get_travel_calculator(self._adr)

        return {
            "sid": self._sid,
            "adr": self._adr,
            "centero_state": state,
            "centero_state_name": STATE_NAMES.get(state, "unknown"),
            "known_state": state in KNOWN_STATES,
            "error_state": state in ERROR_STATES,
            "available_from_gateway": True,
            "fast_polling": bool(self.coordinator._moving_devices),
            "position_source": "time_based" if calc.is_configured else "discrete",
        }

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""

        silent = self.coordinator.is_silent_drive(self._adr)

        LOGGER.debug(
            "Opening cover SID=%s ADR=%s (silent=%s)",
            self._sid,
            self._adr,
            silent,
        )

        await self.coordinator.api.send_command(
            self._adr,
            COMMAND_UP_SILENT if silent else COMMAND_UP,
        )

        self.coordinator.set_optimistic_state(
            self._adr,
            STATE_OPENING,
        )

        await self.coordinator.async_request_refresh()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""

        silent = self.coordinator.is_silent_drive(self._adr)

        LOGGER.debug(
            "Closing cover SID=%s ADR=%s (silent=%s)",
            self._sid,
            self._adr,
            silent,
        )

        await self.coordinator.api.send_command(
            self._adr,
            COMMAND_DOWN_SILENT if silent else COMMAND_DOWN,
        )

        self.coordinator.set_optimistic_state(
            self._adr,
            STATE_CLOSING,
        )

        await self.coordinator.async_request_refresh()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""

        LOGGER.debug(
            "Stopping cover SID=%s ADR=%s",
            self._sid,
            self._adr,
        )

        await self.coordinator.api.send_command(
            self._adr,
            COMMAND_STOP,
        )

        self.coordinator.clear_optimistic_state(
            self._adr,
        )

        #
        # Freeze the time-based estimate at wherever it has reached.
        #
        self.coordinator.stop_travel(
            self._adr,
        )

        await self.coordinator.async_request_refresh()

    async def async_vent_cover(self) -> None:
        """Move the cover to the vent position."""

        LOGGER.debug(
            "Moving cover SID=%s ADR=%s to vent position",
            self._sid,
            self._adr,
        )

        await self.coordinator.api.send_command(
            self._adr,
            COMMAND_VENT,
        )

        #
        # We don't know which way the preset lies, but the gateway
        # reports the movement direction on the next polls, so the
        # position estimate keeps tracking through the transit. Once
        # STATE_VENT (1004) is reported, the reconcile pass resolves
        # the final position (configured value, tracked estimate, or
        # the 50% fallback).
        #
        await self.coordinator.async_request_refresh()

    async def async_favorite_cover(self) -> None:
        """Move the cover to the favorite position."""

        LOGGER.debug(
            "Moving cover SID=%s ADR=%s to favorite position",
            self._sid,
            self._adr,
        )

        await self.coordinator.api.send_command(
            self._adr,
            COMMAND_FAVORITE,
        )

        #
        # We don't know the resulting state or movement direction, so
        # no optimistic override; the gateway reports the direction on
        # the next polls and the position estimate keeps tracking.
        # Once STATE_INTERMEDIATE (1003) is reported, the reconcile
        # pass resolves the final position (configured value, tracked
        # estimate, or the 50% fallback).
        #
        self.coordinator.clear_optimistic_state(
            self._adr,
        )

        await self.coordinator.async_request_refresh()
