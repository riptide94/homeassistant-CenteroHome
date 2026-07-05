"""DataUpdateCoordinator for Centero."""

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CenteroAPI, CenteroApiError
from .const import (
    FAST_POLL_INTERVAL,
    LOGGER,
    POLL_INTERVAL,
    STATE_CLOSING,
    STATE_OPENING,
    KNOWN_STATES,
)


class CenteroCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Coordinate Centero state updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: CenteroAPI,
    ) -> None:
        """Initialize the coordinator."""

        super().__init__(
            hass,
            LOGGER,
            name="Centero",
            update_interval=POLL_INTERVAL,
        )

        self.api = api

        #
        # Optimistic state overrides.
        #
        # Key: adr
        #
        # Example:
        # {
        #     "08": {"state": "100A"},
        #     "09": {"state": "100B"},
        # }
        #
        self._optimistic_states: dict[str, dict[str, Any]] = {}
        self._moving_devices: set[str] = set()

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch data from the gateway."""

        try:
            response = await self.api.get_states()

        except CenteroApiError as err:
            raise UpdateFailed(str(err)) from err

        devices: dict[str, dict[str, Any]] = {}

        for device in response.get("XC_SUC", []):
            if device.get("type") != "ER":
                continue

            adr = device.get("adr")

            if not adr:
                continue

            devices[adr] = {
                "sid": device.get("sid"),
                "adr": adr,
                "state": device.get("state"),
            }

            state = device.get("state")

            if state not in KNOWN_STATES:
                LOGGER.warning(
                    "Unknown Centero state observed: sid=%s adr=%s state=%s",
                    device.get("sid"),
                    adr,
                    state,
                )

        #
        # Merge optimistic states.
        #
        # As soon as the gateway reports a different state,
        # remove the optimistic override.
        #
        for adr, optimistic in list(self._optimistic_states.items()):
            actual = devices.get(adr)

            if actual is None:
                continue

            actual_state = actual["state"]
            optimistic_state = optimistic["state"]

            if actual_state != optimistic_state:
                self._optimistic_states.pop(adr)

                #
                # Movement finished.
                #
                if actual_state not in (STATE_OPENING, STATE_CLOSING):
                    self._moving_devices.discard(adr)
            else:
                actual.update(optimistic)

        for adr, device in devices.items():
            state = device["state"]

            if state in (STATE_OPENING, STATE_CLOSING):
                self._moving_devices.add(adr)
            else:
                self._moving_devices.discard(adr)

        self._update_poll_interval()

        return devices

    def set_optimistic_state(
        self,
        adr: str,
        state: str,
    ) -> None:
        """Set an optimistic state for a device."""

        self._optimistic_states[adr] = {
            "state": state,
        }

        if state in (STATE_OPENING, STATE_CLOSING):
            self._moving_devices.add(adr)

        self._update_poll_interval()

        self.async_update_listeners()

    def clear_optimistic_state(
        self,
        adr: str,
    ) -> None:
        """Clear an optimistic state."""

        if adr in self._optimistic_states:
            self._optimistic_states.pop(adr)

        self._moving_devices.discard(adr)

        self._update_poll_interval()

        self.async_update_listeners()

    def _update_poll_interval(self) -> None:
        """Update polling interval based on movement state."""

        new_interval = FAST_POLL_INTERVAL if self._moving_devices else POLL_INTERVAL

        if self.update_interval != new_interval:
            LOGGER.debug(
                "Changing polling interval from %s to %s",
                self.update_interval,
                new_interval,
            )

            self.update_interval = new_interval
