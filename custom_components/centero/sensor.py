"""Sensor platform for Centero cover state diagnostics."""

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import DOMAIN, STATE_NAMES
from .coordinator import CenteroCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Centero cover state diagnostic sensors."""

    coordinator: CenteroCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities: list[SensorEntity] = []

    for device in coordinator.data.values():
        entities.append(CenteroStateCodeSensor(entry, coordinator, device))
        entities.append(CenteroStateTranslationSensor(entry, coordinator, device))

    async_add_entities(entities)


class CenteroStateSensor(CoordinatorEntity[CenteroCoordinator], SensorEntity):
    """Base for a per-cover sensor reflecting the raw gateway state."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: CenteroCoordinator,
        device: dict[str, Any],
        translation_key: str,
    ) -> None:
        """Initialize the sensor."""

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
        self.entity_id = f"sensor.{slugify(cover_unique)}_{translation_key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information, matching the cover's device."""

        gateway_device_id = self.hass.data[DOMAIN][self._entry.entry_id][
            "gateway_device_id"
        ]

        return DeviceInfo(
            identifiers={(DOMAIN, self._cover_unique_id)},
            manufacturer="Elero",
            model="Centero controlled cover",
            via_device_id=gateway_device_id,
        )

    @property
    def _device_data(self) -> dict[str, Any] | None:
        """Return coordinator data for this cover."""

        return self.coordinator.data.get(self._adr)

    @property
    def available(self) -> bool:
        """Return availability."""

        return super().available and self._device_data is not None


class CenteroStateCodeSensor(CenteroStateSensor):
    """Raw state code last reported by the gateway."""

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: CenteroCoordinator,
        device: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""

        super().__init__(entry, coordinator, device, "state_code")

    @property
    def native_value(self) -> str | None:
        """Return the raw state code."""

        device = self._device_data

        return device["state"] if device is not None else None


class CenteroStateTranslationSensor(CenteroStateSensor):
    """Human-readable translation of the last reported state code."""

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: CenteroCoordinator,
        device: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""

        super().__init__(entry, coordinator, device, "state_translation")

    @property
    def native_value(self) -> str | None:
        """Return the translated name of the state code."""

        device = self._device_data

        if device is None:
            return None

        return STATE_NAMES.get(device["state"], "unknown")
