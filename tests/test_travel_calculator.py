"""Unit tests for the TravelCalculator (no Home Assistant involved)."""

import pytest

from custom_components.centero.travel_calculator import TravelCalculator, TravelStatus

from .common import FakeClock


@pytest.fixture
def clock(monkeypatch) -> FakeClock:
    """Replace the calculator's clock with a controllable one."""

    fake = FakeClock()

    monkeypatch.setattr(
        "custom_components.centero.travel_calculator.time",
        fake,
    )

    return fake


def test_unconfigured_without_travel_times() -> None:
    """Both travel times are required for time-based estimation."""

    calc = TravelCalculator()
    assert not calc.is_configured

    calc.set_travel_time_up(10)
    assert not calc.is_configured

    calc.set_travel_time_down(0)
    assert not calc.is_configured

    calc.set_travel_time_down(20)
    assert calc.is_configured


def test_position_unknown_by_default() -> None:
    """Position starts out unknown."""

    calc = TravelCalculator(10, 10)

    assert calc.position is None
    assert calc.current_position() is None


def test_set_position_clamps() -> None:
    """Calibrated positions are clamped to 0..100."""

    calc = TravelCalculator(10, 10)

    calc.set_position(150)
    assert calc.position == 100

    calc.set_position(-5)
    assert calc.position == 0


def test_set_position_is_idempotent() -> None:
    """Re-seeding the same position, as reconcile does each poll, is stable."""

    calc = TravelCalculator(10, 10)

    calc.set_position(30)
    calc.set_position(30)

    assert calc.position == 30
    assert calc.travel_status == TravelStatus.STOPPED


def test_invalidate() -> None:
    """Invalidating marks the position unknown and stops tracking."""

    calc = TravelCalculator(10, 10)

    calc.set_position(30)
    calc.invalidate()

    assert calc.position is None
    assert not calc.is_traveling


def test_travel_up_interpolates(clock: FakeClock) -> None:
    """Opening interpolates against the up travel time."""

    calc = TravelCalculator(10, 20)

    calc.set_position(0)
    calc.start_travel_up()

    clock.now += 5
    assert calc.current_position() == 50

    clock.now += 10
    assert calc.current_position() == 100


def test_travel_down_interpolates(clock: FakeClock) -> None:
    """Closing interpolates against the down travel time."""

    calc = TravelCalculator(10, 20)

    calc.set_position(100)
    calc.start_travel_down()

    clock.now += 5
    assert calc.current_position() == 75

    clock.now += 30
    assert calc.current_position() == 0


def test_stop_freezes_position(clock: FakeClock) -> None:
    """Stopping freezes the estimate; further time has no effect."""

    calc = TravelCalculator(10, 10)

    calc.set_position(0)
    calc.start_travel_up()

    clock.now += 3
    calc.stop()

    assert calc.position == 30

    clock.now += 5
    assert calc.current_position() == 30


def test_restart_same_direction_keeps_start_point(clock: FakeClock) -> None:
    """Repeated moving reports don't reset the interpolation start."""

    calc = TravelCalculator(10, 10)

    calc.set_position(0)
    calc.start_travel_up()

    clock.now += 3
    calc.start_travel_up()

    clock.now += 2
    assert calc.current_position() == 50


def test_travel_with_unknown_position_stays_unknown(clock: FakeClock) -> None:
    """Tracking movement without a start position yields no estimate."""

    calc = TravelCalculator(10, 10)

    calc.start_travel_up()

    clock.now += 5
    assert calc.current_position() is None
