"""DataUpdateCoordinator for Centero."""

from dataclasses import dataclass
from datetime import datetime
from functools import partial
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HassJob, HomeAssistant
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CenteroAPI, CenteroApiError
from .const import (
    COMMAND_STOP,
    FAST_POLL_INTERVAL,
    LOGGER,
    MOVEMENT_TIMEOUT_DEFAULT_SECONDS,
    MOVEMENT_TIMEOUT_MARGIN_SECONDS,
    MOVING_STATES,
    OPENING_STATES,
    POLL_INTERVAL,
    PRESET_POSITION_DEFAULT,
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


@dataclass
class _PendingPositionStop:
    """A scheduled stop command ending a timed set-position run."""

    opening: bool
    cancel: CALLBACK_TYPE | None = None


class CenteroCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Coordinate Centero state updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api: CenteroAPI,
    ) -> None:
        """Initialize the coordinator."""

        super().__init__(
            hass,
            LOGGER,
            config_entry=config_entry,
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
        # Monotonic timestamp at which each device's current movement
        # started (HA command, or first moving report), used to detect
        # moving states the gateway has kept cached for too long.
        #
        # Key: adr
        #
        self._moving_since: dict[str, float] = {}

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
        # Covers not yet radio-queried since startup. Changes made
        # while HA was not running (e.g. via a wall switch) are not in
        # the gateway's cache, so every cover is queried once, at the
        # fast poll interval, before the regular round-robin takes
        # over. None until the first GetStates reveals the covers.
        #
        self._initial_refresh_pending: set[str] | None = None

        #
        # Silent-drive (quiet/slow travel) preference per device, set via
        # the "Silent drive" switch. Not exposed anywhere by the gateway
        # API; purely a user-set preference.
        #
        # Key: adr
        #
        self._silent_drive: dict[str, bool] = {}

        #
        # User-configured positions of the motor-programmed presets,
        # set via the "Position favorite" / "Position vent" numbers.
        #
        # Key: adr, then preset state (STATE_INTERMEDIATE / STATE_VENT)
        #
        self._preset_positions: dict[str, dict[str, float]] = {}

        #
        # Pending timed stops for set_cover_position runs.
        #
        # Key: adr
        #
        self._position_stops: dict[str, _PendingPositionStop] = {}

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
        # Covers that vanished from the gateway must not keep the
        # sweep (and with it the fast poll interval) running.
        #
        if self._initial_refresh_pending is None:
            self._initial_refresh_pending = set(devices)
        else:
            self._initial_refresh_pending &= set(devices)

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

        now = time.monotonic()

        for adr, device in devices.items():
            state = device["state"]

            if state in MOVING_STATES:
                self._moving_devices.add(adr)
                self._moving_since.setdefault(adr, now)
            else:
                self._moving_devices.discard(adr)
                self._moving_since.pop(adr, None)

        self._reconcile_travel_calculators(devices)

        self._update_poll_interval()

        return devices

    def _pick_refresh_adr(self) -> str | None:
        """Choose which device to radio-query this cycle, if any.

        Covers with an unconfirmed movement take priority: externally
        moving ones (moving state without an optimistic override, i.e.
        not commanded through HA) - the gateway will never notice their
        progress on its own - and HA-commanded ones that have been
        reported moving for longer than they should take, whose end of
        travel the gateway has likely missed. While only HA-commanded
        movement within its expected duration is going on, keep the
        radio clear. Otherwise, after startup, query every cover once;
        then cycle through all covers to bound the staleness of
        physically-triggered changes.
        """

        if not self.data:
            return None

        now = time.monotonic()

        unconfirmed = [
            adr
            for adr in sorted(self._moving_devices)
            if adr not in self._optimistic_states
            or self._is_movement_overdue(adr, now)
        ]

        initial = sorted(self._initial_refresh_pending or ())

        if unconfirmed:
            candidates = unconfirmed
            reason = "unconfirmed movement"
        elif self._moving_devices:
            LOGGER.debug(
                "Skipping RefreshSC, HA-commanded movement in progress: %s",
                sorted(self._moving_devices),
            )
            return None
        elif initial:
            candidates = initial[:1]
            reason = "initial sweep"
        else:
            candidates = sorted(self.data)
            reason = "idle round-robin"

        adr = candidates[self._refresh_counter % len(candidates)]
        self._refresh_counter += 1

        #
        # Any query counts towards the initial sweep. Discard even if
        # the query fails, so an unreachable motor cannot keep the
        # fast poll interval running.
        #
        if self._initial_refresh_pending:
            self._initial_refresh_pending.discard(adr)

        LOGGER.debug(
            "RefreshSC target adr=%s (%s, %d candidate(s))",
            adr,
            reason,
            len(candidates),
        )

        return adr

    def _is_movement_overdue(self, adr: str, now: float) -> bool:
        """Return whether a movement has outlasted its expected duration."""

        since = self._moving_since.get(adr)

        return since is not None and now - since > self._movement_timeout(adr)

    def _movement_timeout(self, adr: str) -> float:
        """Return how long a movement may be reported before re-checking it."""

        calc = self._travel_calculators.get(adr)

        if calc is None:
            return MOVEMENT_TIMEOUT_DEFAULT_SECONDS

        state = self._optimistic_states.get(adr, {}).get("state")

        travel_time = (
            calc.travel_time_up if state in OPENING_STATES else calc.travel_time_down
        )

        if not travel_time:
            return MOVEMENT_TIMEOUT_DEFAULT_SECONDS

        return travel_time + MOVEMENT_TIMEOUT_MARGIN_SECONDS

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

                opening = state in OPENING_STATES

                #
                # The cover was reversed externally (e.g. via a remote)
                # while a timed set-position stop was pending; the stop
                # no longer applies to this movement.
                #
                pending = self._position_stops.get(adr)

                if pending is not None and pending.opening != opening:
                    self.cancel_position_stop(adr)

                if opening:
                    calc.start_travel_up()
                else:
                    calc.start_travel_down()

                continue

            #
            # Any non-moving state means travel has ended (end stop
            # reached early, remote stop, blocking, ...); a pending
            # timed stop must not fire into a later movement.
            #
            self.cancel_position_stop(adr)

            #
            # Freeze a still-running estimate before anything else.
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
                # vent). A user-configured preset position is the best
                # truth; otherwise keep the estimate tracked during the
                # move there, and only fall back to the flat guess when
                # no estimate exists at all.
                #
                configured = self.configured_preset_position(adr, state)

                if configured is not None:
                    calc.set_position(configured)
                elif calc.position is None:
                    calc.set_position(PRESET_POSITION_DEFAULT)
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

        #
        # A new commanded movement supersedes any pending timed stop;
        # set_cover_position re-schedules its own stop afterwards.
        #
        self.cancel_position_stop(adr)

        self._optimistic_states[adr] = {
            "state": state,
        }

        if state in MOVING_STATES:
            self._moving_devices.add(adr)

            #
            # A new command starts a new movement, with a fresh
            # expected duration.
            #
            self._moving_since[adr] = time.monotonic()

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

        self.cancel_position_stop(adr)

        if adr in self._optimistic_states:
            self._optimistic_states.pop(adr)

        self._moving_devices.discard(adr)
        self._moving_since.pop(adr, None)

        self._update_poll_interval()

        self.async_update_listeners()

    def set_silent_drive(self, adr: str, enabled: bool) -> None:
        """Set whether a device should use silent-drive commands."""

        self._silent_drive[adr] = enabled

    def is_silent_drive(self, adr: str) -> bool:
        """Return whether a device is set to use silent-drive commands."""

        return self._silent_drive.get(adr, False)

    def set_preset_position(self, adr: str, state: str, position: float) -> None:
        """Set the configured position of a preset state for a device."""

        self._preset_positions.setdefault(adr, {})[state] = position

        #
        # If the cover currently sits at this preset, apply the value
        # right away instead of waiting for the next poll. This also
        # covers startup, where the first refresh runs before the
        # number entities have restored their values.
        #
        device = (self.data or {}).get(adr)

        if device is not None and device["state"] == state:
            self.get_travel_calculator(adr).set_position(position)

            self.async_update_listeners()

    def configured_preset_position(self, adr: str, state: str) -> int | None:
        """Return the configured position of a preset state, if any."""

        position = self._preset_positions.get(adr, {}).get(state)

        if position is None:
            return None

        return round(position)

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

    def schedule_position_stop(self, adr: str, opening: bool, delay: float) -> None:
        """Schedule the stop command that ends a timed set-position run."""

        self.cancel_position_stop(adr)

        pending = _PendingPositionStop(opening=opening)

        #
        # cancel_on_shutdown: when HA shuts down mid-run the stop is
        # dropped and the motor runs to its end stop, matching the
        # restart-mid-travel behavior.
        #
        pending.cancel = async_call_later(
            self.hass,
            delay,
            HassJob(
                partial(self._async_position_stop_fired, adr, pending),
                f"centero position stop {adr}",
                cancel_on_shutdown=True,
            ),
        )

        self._position_stops[adr] = pending

        LOGGER.debug(
            "Scheduled position stop for adr=%s in %.2fs (opening=%s)",
            adr,
            delay,
            opening,
        )

    def cancel_position_stop(self, adr: str) -> None:
        """Cancel a pending timed set-position stop, if any."""

        pending = self._position_stops.pop(adr, None)

        if pending is None:
            return

        if pending.cancel is not None:
            pending.cancel()

        LOGGER.debug("Cancelled pending position stop for adr=%s", adr)

    async def _async_position_stop_fired(
        self,
        adr: str,
        pending: _PendingPositionStop,
        _fired_at: datetime,
    ) -> None:
        """Send the stop that ends a timed set-position run."""

        #
        # The loop can fire the timer in the same iteration as a
        # cancel, and a new run may have been scheduled since; only
        # act if this is still the registered pending stop.
        #
        if self._position_stops.get(adr) is not pending:
            return

        del self._position_stops[adr]

        LOGGER.debug("Timed position stop for adr=%s", adr)

        try:
            await self.api.send_command(adr, COMMAND_STOP)

        except CenteroApiError as err:
            #
            # The motor keeps moving; leave the estimate travelling so
            # it stays consistent with reality, and let the reconcile
            # pass recalibrate at the end stop.
            #
            LOGGER.warning(
                "Failed to send timed position stop for adr=%s: %s",
                adr,
                err,
            )
            return

        self.clear_optimistic_state(adr)

        #
        # Freeze only after the stop command's round-trip, so the
        # estimate absorbs most of the command latency.
        #
        self.stop_travel(adr)

        await self.async_request_refresh()

    async def async_shutdown(self) -> None:
        """Cancel pending position stops and shut down the coordinator."""

        for adr in list(self._position_stops):
            self.cancel_position_stop(adr)

        await super().async_shutdown()

    def _update_poll_interval(self) -> None:
        """Update polling interval based on movement state."""

        new_interval = (
            FAST_POLL_INTERVAL
            if self._moving_devices or self._initial_refresh_pending
            else POLL_INTERVAL
        )

        if self.update_interval != new_interval:
            LOGGER.debug(
                "Changing polling interval from %s to %s",
                self.update_interval,
                new_interval,
            )

            self.update_interval = new_interval
