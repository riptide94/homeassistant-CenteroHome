"""DataUpdateCoordinator for Centero."""

import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CenteroAPI, CenteroApiError
from .const import (
    FAST_POLL_INTERVAL,
    LOGGER,
    MOVING_STATES,
    OPENING_STATES,
    POLL_INTERVAL,
    PRESET_STATES,
    STATE_BOTTOM_INTERMEDIATE,
    STATE_CLOSED,
    STATE_OPEN,
    STATE_PARTIAL,
    STATE_TOP_TILT,
    TRAVEL_STOP_GRACE_SECONDS,
    KNOWN_STATES,
)
from .travel_calculator import TravelCalculator


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

        #
        # Time-based position estimation.
        #
        # Key: adr
        #
        self._travel_calculators: dict[str, TravelCalculator] = {}

        #
        # Monotonic timestamp of the last HA-issued stop per device,
        # used to ignore stale moving states reported by the gateway
        # right after the stop.
        #
        # Key: adr
        #
        self._travel_stop_times: dict[str, float] = {}

        #
        # Round-robin counter for RefreshSC radio queries.
        #
        self._refresh_counter = 0

        #
        # Silent-drive (quiet/slow travel) preference per device, set via
        # the "Silent drive" switch. Not exposed anywhere by the gateway
        # API; purely a user-set preference.
        #
        # Key: adr
        #
        self._silent_drive: dict[str, bool] = {}

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch data from the gateway."""

        #
        # The gateway does not notice movements it did not command
        # itself (e.g. via a physical remote), so we make it radio-query
        # one motor per cycle before reading the cached states.
        #
        refreshed = await self._async_refresh_one_device()

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
        # The RefreshSC result is at least as fresh as the cached
        # GetStates snapshot; make sure it wins.
        #
        if refreshed is not None and refreshed["adr"] in devices:
            devices[refreshed["adr"]]["state"] = refreshed["state"]

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
                if actual_state not in MOVING_STATES:
                    self._moving_devices.discard(adr)
            else:
                actual.update(optimistic)

        for adr, device in devices.items():
            state = device["state"]

            if state in MOVING_STATES:
                self._moving_devices.add(adr)
            else:
                self._moving_devices.discard(adr)

        self._reconcile_travel_calculators(devices)

        self._update_poll_interval()

        return devices

    def _pick_refresh_adr(self) -> str | None:
        """Choose which device to radio-query this cycle, if any.

        Externally-moving covers (moving state without an optimistic
        override, i.e. not commanded through HA) take priority - the
        gateway will never notice their progress on its own. When
        everything is idle, cycle through all covers to bound the
        staleness of physically-triggered changes. While only
        HA-commanded movement is going on, keep the radio clear.
        """

        if not self.data:
            return None

        external = [
            adr
            for adr in sorted(self._moving_devices)
            if adr not in self._optimistic_states
        ]

        if external:
            candidates = external
            reason = "externally moving"
        elif not self._moving_devices:
            candidates = sorted(self.data)
            reason = "idle round-robin"
        else:
            LOGGER.debug(
                "Skipping RefreshSC, HA-commanded movement in progress: %s",
                sorted(self._moving_devices),
            )
            return None

        adr = candidates[self._refresh_counter % len(candidates)]
        self._refresh_counter += 1

        LOGGER.debug(
            "RefreshSC target adr=%s (%s, %d candidate(s))",
            adr,
            reason,
            len(candidates),
        )

        return adr

    async def _async_refresh_one_device(self) -> dict[str, Any] | None:
        """Radio-query one device and return its fresh record, if any."""

        adr = self._pick_refresh_adr()

        if adr is None:
            return None

        try:
            response = await self.api.refresh_state(adr)

        except CenteroApiError as err:
            #
            # Best effort - the regular GetStates poll still runs.
            #
            LOGGER.debug("RefreshSC failed for adr=%s: %s", adr, err)
            return None

        device = response.get("XC_SUC")

        if (
            isinstance(device, dict)
            and device.get("adr") == adr
            and device.get("state")
        ):
            LOGGER.debug(
                "RefreshSC adr=%s returned state=%s",
                adr,
                device["state"],
            )
            return device

        LOGGER.debug("Unexpected RefreshSC response for adr=%s: %s", adr, response)

        return None

    def _reconcile_travel_calculators(
        self,
        devices: dict[str, dict[str, Any]],
    ) -> None:
        """Keep time-based position estimates in sync with observed states.

        This also picks up movement that HA did not initiate itself, e.g.
        a cover operated through the original remote, within one poll cycle.
        """

        for adr, device in devices.items():
            calc = self.get_travel_calculator(adr)
            state = device["state"]

            if state in MOVING_STATES:
                #
                # The gateway keeps reporting the old moving state for
                # a short while after we commanded a stop; don't let
                # that restart the estimate we just froze.
                #
                if self._within_stop_grace(adr):
                    continue

                if state in OPENING_STATES:
                    calc.start_travel_up()
                else:
                    calc.start_travel_down()

                continue

            #
            # Any non-moving state means travel has ended; freeze a
            # still-running estimate before anything else.
            #
            if calc.is_traveling:
                calc.stop()

            self._travel_stop_times.pop(adr, None)

            if state in (STATE_OPEN, STATE_TOP_TILT):
                calc.set_position(100)
            elif state in (STATE_CLOSED, STATE_BOTTOM_INTERMEDIATE):
                calc.set_position(0)
            elif state in PRESET_STATES:
                #
                # The cover sits at a user-defined preset (favorite or
                # vent) whose actual position we cannot know.
                #
                calc.invalidate()
            elif state == STATE_PARTIAL:
                #
                # Only fall back to the flat guess when we have no
                # time-based estimate at all; a frozen estimate is
                # more precise than a fixed 50%.
                #
                if calc.position is None:
                    calc.set_position(50)

    def _within_stop_grace(self, adr: str) -> bool:
        """Return whether a device was stopped by HA very recently."""

        stop_time = self._travel_stop_times.get(adr)

        return (
            stop_time is not None
            and time.monotonic() - stop_time < TRAVEL_STOP_GRACE_SECONDS
        )

    def set_optimistic_state(
        self,
        adr: str,
        state: str,
    ) -> None:
        """Set an optimistic state for a device."""

        self._optimistic_states[adr] = {
            "state": state,
        }

        if state in MOVING_STATES:
            self._moving_devices.add(adr)

            #
            # A new commanded movement supersedes any recent stop.
            #
            self._travel_stop_times.pop(adr, None)

            #
            # Start the position estimate moving immediately, rather
            # than waiting for the next poll to confirm it.
            #
            calc = self.get_travel_calculator(adr)

            if state in OPENING_STATES:
                calc.start_travel_up()
            else:
                calc.start_travel_down()

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

    def set_silent_drive(self, adr: str, enabled: bool) -> None:
        """Set whether a device should use silent-drive commands."""

        self._silent_drive[adr] = enabled

    def is_silent_drive(self, adr: str) -> bool:
        """Return whether a device is set to use silent-drive commands."""

        return self._silent_drive.get(adr, False)

    def get_travel_calculator(self, adr: str) -> TravelCalculator:
        """Return the travel calculator for a device, creating it if needed."""

        if adr not in self._travel_calculators:
            self._travel_calculators[adr] = TravelCalculator()

        return self._travel_calculators[adr]

    def stop_travel(self, adr: str) -> None:
        """Freeze the position estimate for a device at its current value."""

        self.get_travel_calculator(adr).stop()

        self._travel_stop_times[adr] = time.monotonic()

        self.async_update_listeners()

    def invalidate_travel(self, adr: str) -> None:
        """Mark the position estimate for a device as unknown.

        Used when a cover is sent to a position we cannot predict,
        such as a favorite or vent preset.
        """

        self.get_travel_calculator(adr).invalidate()

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
