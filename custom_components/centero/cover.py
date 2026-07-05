"""Cover platform for Centero."""

from typing import Any

from homeassistant.components.cover import CoverEntity, CoverEntityFeature
from homeassistant.config_entries import ConfigEntry

# from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    COMMAND_DOWN,
    COMMAND_FAVORITE,
    COMMAND_STOP,
    COMMAND_UP,
    COMMAND_VENT,
    DOMAIN,
    LOGGER,
    STATE_CLOSED,
    STATE_CLOSING,
    STATE_OPEN,
    STATE_OPENING,
    STATE_PARTIAL,
    # STATE_VENTING,
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

        #
        # Entity name:
        #
        # cover.elero_sid01_adr03
        #
        self._attr_name = f"Elero SID{self._sid} ADR{self._adr}"

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

        if state == STATE_CLOSED:
            return True

        if state in (
            STATE_OPEN,
            STATE_PARTIAL,
            STATE_OPENING,
            STATE_CLOSING,
            # STATE_VENTING,
        ):
            return False

        return None

    @property
    def is_opening(self) -> bool:
        """Return whether the cover is opening."""

        device = self._device_data

        return device is not None and device["state"] == STATE_OPENING

    @property
    def current_cover_position(self):
        """Return the current position of the cover."""

        device = self._device_data

        if device is None:
            return None

        state = device["state"]

        if state == STATE_OPEN:
            return 100

        if state == STATE_CLOSED:
            return 0

        if state == STATE_PARTIAL:
            return 50

        return None

    @property
    def is_closing(self) -> bool:
        """Return whether the cover is closing."""

        device = self._device_data

        return device is not None and device["state"] == STATE_CLOSING

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

        return {
            "sid": self._sid,
            "adr": self._adr,
            "centero_state": state,
            "known_state": state
            in {
                STATE_OPEN,
                STATE_CLOSED,
                STATE_PARTIAL,
                STATE_OPENING,
                STATE_CLOSING,
                # STATE_VENTING,
            },
            "available_from_gateway": True,
            "fast_polling": bool(self.coordinator._moving_devices),
        }

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""

        LOGGER.debug(
            "Opening cover SID=%s ADR=%s",
            self._sid,
            self._adr,
        )

        await self.coordinator.api.send_command(
            self._adr,
            COMMAND_UP,
        )

        self.coordinator.set_optimistic_state(
            self._adr,
            STATE_OPENING,
        )

        await self.coordinator.async_request_refresh()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""

        LOGGER.debug(
            "Closing cover SID=%s ADR=%s",
            self._sid,
            self._adr,
        )

        await self.coordinator.api.send_command(
            self._adr,
            COMMAND_DOWN,
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

        #
        # We don't know the resulting position yet.
        #
        self.coordinator.clear_optimistic_state(
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

    # self.coordinator.set_optimistic_state(
    #     self._adr,
    #     STATE_VENTING,
    # )

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
    # We don't know the resulting state.
    #
    self.coordinator.clear_optimistic_state(
        self._adr,
    )

    await self.coordinator.async_request_refresh()
