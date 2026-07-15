"""Time-based travel position estimation for covers without position feedback."""

from enum import Enum, auto
import time


class TravelStatus(Enum):
    """Movement status of a cover being tracked."""

    STOPPED = auto()
    TRAVELLING_UP = auto()
    TRAVELLING_DOWN = auto()


class TravelCalculator:
    """Estimate cover position from elapsed travel time.

    Position follows HA convention: 0 = closed, 100 = open.
    Up and down travel times are tracked separately since covers
    commonly take a different amount of time to open than to close.
    """

    def __init__(
        self,
        travel_time_up: float | None = None,
        travel_time_down: float | None = None,
    ) -> None:
        """Initialize the calculator."""

        self.travel_time_up = travel_time_up
        self.travel_time_down = travel_time_down

        self.position: float | None = None
        self.travel_status = TravelStatus.STOPPED

        self._start_position: float | None = None
        self._start_time: float | None = None

    @property
    def is_configured(self) -> bool:
        """Return whether both travel times are known and usable."""

        return (
            self.travel_time_up is not None
            and self.travel_time_up > 0
            and self.travel_time_down is not None
            and self.travel_time_down > 0
        )

    @property
    def is_traveling(self) -> bool:
        """Return whether the cover is currently being tracked as moving."""

        return self.travel_status != TravelStatus.STOPPED

    def set_travel_time_up(self, travel_time_up: float | None) -> None:
        """Update the up travel time, taking effect immediately."""

        self.travel_time_up = travel_time_up

    def set_travel_time_down(self, travel_time_down: float | None) -> None:
        """Update the down travel time, taking effect immediately."""

        self.travel_time_down = travel_time_down

    def set_position(self, position: float) -> None:
        """Hard-calibrate the current position, e.g. on a confirmed endpoint."""

        self.position = min(100.0, max(0.0, position))
        self.travel_status = TravelStatus.STOPPED
        self._start_position = None
        self._start_time = None

    def start_travel_up(self) -> None:
        """Start tracking upward (opening) movement."""

        self._start_travel(TravelStatus.TRAVELLING_UP)

    def start_travel_down(self) -> None:
        """Start tracking downward (closing) movement."""

        self._start_travel(TravelStatus.TRAVELLING_DOWN)

    def _start_travel(self, status: TravelStatus) -> None:
        """Begin tracking movement in the given direction."""

        if self.travel_status == status:
            #
            # Already tracking this direction, don't reset the start point.
            #
            return

        self._start_position = self.current_position()
        self._start_time = time.monotonic()
        self.travel_status = status

    def stop(self) -> None:
        """Freeze the position estimate at its current value."""

        self.position = self.current_position()
        self.travel_status = TravelStatus.STOPPED
        self._start_position = None
        self._start_time = None

    def invalidate(self) -> None:
        """Mark the position as unknown, e.g. after a move to an unknown preset."""

        self.position = None
        self.travel_status = TravelStatus.STOPPED
        self._start_position = None
        self._start_time = None

    def current_position(self) -> float | None:
        """Return the current estimated position."""

        if self.travel_status == TravelStatus.STOPPED or self._start_time is None:
            return self.position

        if self._start_position is None:
            return self.position

        travel_time = (
            self.travel_time_up
            if self.travel_status == TravelStatus.TRAVELLING_UP
            else self.travel_time_down
        )

        if not travel_time:
            return self._start_position

        elapsed = time.monotonic() - self._start_time
        delta = (elapsed / travel_time) * 100

        if self.travel_status == TravelStatus.TRAVELLING_UP:
            return min(100.0, self._start_position + delta)

        return max(0.0, self._start_position - delta)
