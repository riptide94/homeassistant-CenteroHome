"""API wrapper for Centero."""

import asyncio

from aiohttp import ClientError, ClientSession

from .const import DEFAULT_TIMEOUT


class CenteroApiError(Exception):
    """Raised when the Centero API cannot be reached."""


class CenteroAuthenticationError(CenteroApiError):
    """Placeholder for future authentication support."""


class CenteroAPI:
    """Simple Centero API client."""

    def __init__(self, session: ClientSession, host: str) -> None:
        """CTOR for the API."""
        self._session = session
        self._host = host

    async def _get(self, path: str, params: dict | None = None) -> dict:
        """Perform GET request."""

        url = f"http://{self._host}/{path}"

        try:
            async with asyncio.timeout(DEFAULT_TIMEOUT):
                async with self._session.get(url, params=params) as response:
                    response.raise_for_status()
                    return await response.json(content_type=None)

        except TimeoutError as err:
            raise CenteroApiError("Connection timed out") from err

        except ClientError as err:
            raise CenteroApiError(f"Request failed: {err}") from err

    async def get_info(self) -> dict:
        """Fetch gateway information."""

        return await self._get("info")

    async def get_states(self) -> dict:
        """Fetch all device states as cached by the gateway."""

        return await self._get(
            "cmd",
            params={
                "XC_FNC": "GetStates",
            },
        )

    async def refresh_state(self, address: str) -> dict:
        """Make the gateway radio-query a single blind and return its state.

        Unlike get_states, this reflects movements the gateway did not
        initiate itself (e.g. via a physical remote). The radio round
        trip is typically fast (measured <150ms total), but the elero
        protocol only guarantees an answer within 4 seconds.
        """

        return await self._get(
            "cmd",
            params={
                "XC_FNC": "RefreshSC",
                "type": "ER",
                "adr": address,
            },
        )

    async def send_command(self, address: str, command: str) -> None:
        """Send command to a blind."""

        await self._get(
            "cmd",
            params={
                "XC_FNC": "SendSC",
                "type": "ER",
                "data": f"{address}{command}",
            },
        )
