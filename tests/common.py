"""Shared helpers for Centero tests."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.centero.const import DOMAIN, STATE_CLOSED

MOCK_SID = "01"
MOCK_ADR = "03"

COVER_UNIQUE_ID = f"elero_sid{MOCK_SID}_adr{MOCK_ADR}"


class FakeClock:
    """Controllable monotonic clock."""

    def __init__(self) -> None:
        """Initialize the clock."""

        self.now = 1000.0

    def monotonic(self) -> float:
        """Return the current fake time."""

        return self.now


class MockCenteroAPI:
    """Gateway double with a single ER cover whose state tests can set."""

    def __init__(self) -> None:
        """Initialize the mock gateway."""

        self.state = STATE_CLOSED
        self.sent_commands: list[tuple[str, str]] = []

    async def get_info(self) -> dict:
        """Return gateway information."""

        return {
            "XC_SUC": {
                "name": "Test Gateway",
                "mac": "aa:bb:cc:dd:ee:ff",
                "mhv": "A1",
                "mfv": "1.0",
            }
        }

    async def get_states(self) -> dict:
        """Return the cached device states."""

        return {
            "XC_SUC": [
                {
                    "type": "ER",
                    "sid": MOCK_SID,
                    "adr": MOCK_ADR,
                    "state": self.state,
                }
            ]
        }

    async def refresh_state(self, address: str) -> dict:
        """Return the radio-queried state of a single device."""

        return {
            "XC_SUC": {
                "type": "ER",
                "sid": MOCK_SID,
                "adr": address,
                "state": self.state,
            }
        }

    async def send_command(self, address: str, command: str) -> None:
        """Record a sent command."""

        self.sent_commands.append((address, command))


async def setup_integration(hass: HomeAssistant, entry) -> None:
    """Set up a Centero config entry and wait for it to settle."""

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def poll(hass: HomeAssistant, entry) -> None:
    """Run one coordinator refresh cycle."""

    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    await coordinator.async_refresh()
    await hass.async_block_till_done()


def find_entity_id(hass: HomeAssistant, platform: str, unique_id: str) -> str:
    """Look up an entity id by its unique id."""

    registry = er.async_get(hass)

    entity_id = registry.async_get_entity_id(platform, DOMAIN, unique_id)

    assert entity_id is not None

    return entity_id


async def set_number(hass: HomeAssistant, entity_id: str, value: float) -> None:
    """Set a number entity's value via the service call."""

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": entity_id, "value": value},
        blocking=True,
    )
    await hass.async_block_till_done()
