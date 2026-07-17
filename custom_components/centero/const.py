"""Constants for the Centero integration."""

from datetime import timedelta
import logging

DOMAIN = "centero"

LOGGER = logging.getLogger(__package__)

PLATFORMS = ["cover", "number", "switch"]

DEFAULT_TIMEOUT = 10

POLL_INTERVAL = timedelta(seconds=5)
FAST_POLL_INTERVAL = timedelta(seconds=1)

TRAVEL_TIME_MIN = 1
TRAVEL_TIME_MAX = 300
TRAVEL_TIME_STEP = 0.5

PRESET_POSITION_MIN = 0
PRESET_POSITION_MAX = 100
PRESET_POSITION_STEP = 1

#
# Reported position for a preset state when the user has not
# configured the preset's position and no tracked estimate exists.
#
PRESET_POSITION_DEFAULT = 50

#
# After we command a stop, the gateway keeps reporting the old
# moving state for a short while. Ignore those stale reports so
# they don't restart the travel estimate.
#
TRAVEL_STOP_GRACE_SECONDS = 5.0

#
# Cover states reported by the gateway for ER devices.
#
# Format: "10" followed by the elero status byte from the elero
# Transmitter Stick ("Easy Control") protocol.
#
STATE_NO_INFO = "1000"  # no information
STATE_OPEN = "1001"  # top position stop
STATE_CLOSED = "1002"  # bottom position stop
STATE_INTERMEDIATE = "1003"  # intermediate position stop (favorite preset)
STATE_VENT = "1004"  # tilt / ventilation position stop
STATE_BLOCKING = "1005"  # blocking detected
STATE_OVERHEATED = "1006"  # motor overheated
STATE_TIMEOUT = "1007"  # timeout / motor did not answer
STATE_START_OPENING = "1008"  # start to move up
STATE_START_CLOSING = "1009"  # start to move down
STATE_OPENING = "100A"  # moving up
STATE_CLOSING = "100B"  # moving down
STATE_UNKNOWN = "100C"  # seen in the wild, not documented in the elero protocol
STATE_PARTIAL = "100D"  # stopped in undefined position
STATE_TOP_TILT = "100E"  # top position stop (= tilt position)
STATE_BOTTOM_INTERMEDIATE = "100F"  # bottom position stop (= intermediate position)

OPENING_STATES = {STATE_START_OPENING, STATE_OPENING}
CLOSING_STATES = {STATE_START_CLOSING, STATE_CLOSING}
MOVING_STATES = OPENING_STATES | CLOSING_STATES

#
# Stationary at a user-defined preset. The gateway never reports where
# the preset lies; the user can configure it per cover via the
# "Favorite position" / "Vent position" number entities.
#
PRESET_STATES = {STATE_INTERMEDIATE, STATE_VENT}

ERROR_STATES = {STATE_BLOCKING, STATE_OVERHEATED, STATE_TIMEOUT}

STATE_NAMES = {
    STATE_NO_INFO: "no_information",
    STATE_OPEN: "open",
    STATE_CLOSED: "closed",
    STATE_INTERMEDIATE: "intermediate",
    STATE_VENT: "vent",
    STATE_BLOCKING: "blocking",
    STATE_OVERHEATED: "overheated",
    STATE_TIMEOUT: "timeout",
    STATE_START_OPENING: "start_opening",
    STATE_START_CLOSING: "start_closing",
    STATE_OPENING: "opening",
    STATE_CLOSING: "closing",
    STATE_UNKNOWN: "unknown",
    STATE_PARTIAL: "stopped_undefined",
    STATE_TOP_TILT: "open_tilt",
    STATE_BOTTOM_INTERMEDIATE: "closed_intermediate",
}

KNOWN_STATES = set(STATE_NAMES)

COMMAND_DOWN = "00"
COMMAND_UP = "01"
COMMAND_STOP = "02"
COMMAND_VENT = "0A"
COMMAND_FAVORITE = "0B"
COMMAND_DOWN_SILENT = "1A"
COMMAND_UP_SILENT = "19"
