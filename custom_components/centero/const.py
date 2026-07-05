"""Constants for the Centero integration."""

from datetime import timedelta
import logging

DOMAIN = "centero"

LOGGER = logging.getLogger(__package__)

CONF_HOST = "host"

PLATFORMS = ["cover"]

DEFAULT_TIMEOUT = 10

POLL_INTERVAL = timedelta(seconds=5)
FAST_POLL_INTERVAL = timedelta(seconds=1)

STATE_OPEN = "1001"
STATE_CLOSED = "1002"
STATE_PARTIAL = "1003"
STATE_OPENING = "100A"
STATE_CLOSING = "100B"
STATE_UNKNOWN = "100C"
STATE_VENTING = "100D"

KNOWN_STATES = {
    STATE_OPEN,
    STATE_CLOSED,
    STATE_PARTIAL,
    STATE_OPENING,
    STATE_CLOSING,
    STATE_UNKNOWN,
    STATE_VENTING,
}

COMMAND_DOWN = "00"
COMMAND_UP = "01"
COMMAND_STOP = "02"
COMMAND_VENT = "0A"
COMMAND_FAVORITE = "0B"
