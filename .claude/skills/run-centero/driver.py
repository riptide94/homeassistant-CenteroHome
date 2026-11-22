#!/usr/bin/env python3
"""Interactive driver for the Centero Home Assistant integration.

Boots a REAL Home Assistant core (homeassistant.core.HomeAssistant, not a
mock) with the actual custom_components/centero code loaded from this repo,
and points it at an in-process aiohttp server that speaks the same minimal
JSON protocol as a real Centero gateway (GET /info, GET /cmd?XC_FNC=...).

Only the physical gateway is faked -- everything else (config flow/entry
setup, coordinator polling, entities, services, the real aiohttp client
requests the integration makes) is the real integration code running
inside a real HA core. This is a stronger check than the pytest suite,
which patches CenteroAPI out entirely; here the real HTTP client hits a
real (if fake) HTTP server.

Usage (from repo root):
    .venv/bin/python .claude/skills/run-centero/driver.py

Reads newline-delimited commands from stdin, writes one JSON object per
line to stdout as the response. Commands:

    states                                   dump every entity's state
    state <entity_id>                        dump one entity's state
    call <domain> <service> <entity_id> [k=v ...]
                                              call a HA service; v is
                                              parsed as JSON if possible
                                              (so 12.5, true, "x" all work),
                                              otherwise kept as a raw string
    gw-devices                               dump the fake gateway's devices
    gw-set <adr> <state_code>                set a device's reported state
                                              (e.g. `gw-set 03 1001` = open)
    gw-add <sid> <adr> <state_code>          add a new fake ER device
    refresh                                  run one coordinator poll cycle
    sleep <seconds>                          await asyncio.sleep(seconds)
    help                                     list commands
    quit | exit                              clean shutdown

Example session:
    $ .venv/bin/python .claude/skills/run-centero/driver.py <<'EOF'
    states
    call cover open_cover cover.elero_sid01_adr03
    gw-set 03 1001
    refresh
    state cover.elero_sid01_adr03
    quit
    EOF
"""

import asyncio
import json
import os
import sys
import tempfile
from unittest.mock import patch

from aiohttp import web
from aiohttp.resolver import AsyncResolver

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, REPO_ROOT)

from homeassistant import loader  # noqa: E402
from homeassistant.const import CONF_HOST  # noqa: E402
from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.helpers import frame  # noqa: E402
from pytest_homeassistant_custom_component.common import (  # noqa: E402
    MockConfigEntry,
    async_test_home_assistant,
)

from custom_components.centero.const import DOMAIN, STATE_CLOSED  # noqa: E402

# Same default device as tests/common.py, so behavior lines up with the
# pytest suite's fixtures.
DEFAULT_SID = "01"
DEFAULT_ADR = "03"


class FakeGateway:
    """Minimal stand-in for a real Centero gateway's HTTP API."""

    def __init__(self) -> None:
        self.devices: dict[str, dict[str, str]] = {
            DEFAULT_ADR: {"sid": DEFAULT_SID, "state": STATE_CLOSED}
        }
        self.sent_commands: list[tuple[str, str]] = []
        self.runner: web.AppRunner | None = None
        self.port: int | None = None

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/info", self._handle_info)
        app.router.add_get("/cmd", self._handle_cmd)

        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.port = site._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self.runner is not None:
            await self.runner.cleanup()

    async def _handle_info(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                "XC_SUC": {
                    "name": "Fake Centero Gateway",
                    "mac": "aa:bb:cc:dd:ee:ff",
                    "mhv": "A1",
                    "mfv": "1.0",
                }
            }
        )

    async def _handle_cmd(self, request: web.Request) -> web.Response:
        fnc = request.query.get("XC_FNC")

        if fnc == "GetStates":
            return web.json_response(
                {
                    "XC_SUC": [
                        {"type": "ER", "sid": d["sid"], "adr": adr, "state": d["state"]}
                        for adr, d in self.devices.items()
                    ]
                }
            )

        if fnc == "RefreshSC":
            adr = request.query["adr"]
            d = self.devices[adr]
            return web.json_response(
                {"XC_SUC": {"type": "ER", "sid": d["sid"], "adr": adr, "state": d["state"]}}
            )

        if fnc == "SendSC":
            data = request.query["data"]
            adr, command = data[:2], data[2:]
            self.sent_commands.append((adr, command))
            return web.json_response({"XC_SUC": {}})

        return web.json_response({"error": f"unknown XC_FNC {fnc}"}, status=400)


def _parse_kv(token: str) -> tuple[str, object]:
    key, _, raw = token.partition("=")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = raw
    return key, value


def _entity_json(hass: HomeAssistant, entity_id: str) -> dict:
    state = hass.states.get(entity_id)
    if state is None:
        return {"entity_id": entity_id, "error": "not found"}
    return {
        "entity_id": state.entity_id,
        "state": state.state,
        "attributes": dict(state.attributes),
    }


async def run() -> None:
    gateway = FakeGateway()
    await gateway.start()

    config_dir = tempfile.mkdtemp(prefix="centero-ha-")
    os.symlink(
        os.path.join(REPO_ROOT, "custom_components"),
        os.path.join(config_dir, "custom_components"),
    )

    # Home Assistant's real aiohttp client session wiring reaches into the
    # zeroconf/network components to build a DNS resolver. We don't load
    # those components (we only need `centero`), so swap in a plain
    # resolver -- this mirrors pytest-homeassistant-custom-component's own
    # `mock_zeroconf_resolver` fixture.
    resolver = AsyncResolver()
    resolver.real_close = resolver.close
    resolver_patch = patch(
        "homeassistant.helpers.aiohttp_client._async_make_resolver",
        return_value=resolver,
    )
    resolver_patch.start()

    async with async_test_home_assistant(config_dir=config_dir) as hass:
        hass.data.pop(loader.DATA_CUSTOM_COMPONENTS, None)
        frame.async_setup(hass)

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_HOST: f"127.0.0.1:{gateway.port}"},
        )
        entry.add_to_hass(hass)

        setup_ok = await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        print(
            json.dumps(
                {
                    "event": "ready",
                    "setup_ok": setup_ok,
                    "gateway_port": gateway.port,
                    "entities": [s.entity_id for s in hass.states.async_all()],
                }
            ),
            flush=True,
        )

        loop = asyncio.get_running_loop()
        coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                break

            line = line.strip()
            if not line:
                continue

            parts = line.split()
            cmd, args = parts[0], parts[1:]

            try:
                if cmd in ("quit", "exit"):
                    break

                if cmd == "help":
                    print(json.dumps({"help": __doc__}), flush=True)

                elif cmd == "states":
                    print(
                        json.dumps(
                            [
                                _entity_json(hass, s.entity_id)
                                for s in hass.states.async_all()
                            ]
                        ),
                        flush=True,
                    )

                elif cmd == "state":
                    (entity_id,) = args
                    print(json.dumps(_entity_json(hass, entity_id)), flush=True)

                elif cmd == "call":
                    domain, service, entity_id, *kv = args
                    data = {"entity_id": entity_id}
                    for tok in kv:
                        k, v = _parse_kv(tok)
                        data[k] = v
                    await hass.services.async_call(domain, service, data, blocking=True)
                    await hass.async_block_till_done()
                    print(
                        json.dumps(
                            {"called": [domain, service, data], "result": _entity_json(hass, entity_id)}
                        ),
                        flush=True,
                    )

                elif cmd == "gw-devices":
                    print(
                        json.dumps(
                            {"devices": gateway.devices, "sent_commands": gateway.sent_commands}
                        ),
                        flush=True,
                    )

                elif cmd == "gw-set":
                    adr, state = args
                    gateway.devices[adr]["state"] = state
                    print(json.dumps({"ok": True, "devices": gateway.devices}), flush=True)

                elif cmd == "gw-add":
                    sid, adr, state = args
                    gateway.devices[adr] = {"sid": sid, "state": state}
                    print(json.dumps({"ok": True, "devices": gateway.devices}), flush=True)

                elif cmd == "refresh":
                    await coordinator.async_refresh()
                    await hass.async_block_till_done()
                    print(json.dumps({"ok": True}), flush=True)

                elif cmd == "sleep":
                    (seconds,) = args
                    await asyncio.sleep(float(seconds))
                    print(json.dumps({"ok": True}), flush=True)

                else:
                    print(json.dumps({"error": f"unknown command {cmd!r}"}), flush=True)

            except Exception as err:  # noqa: BLE001
                print(json.dumps({"error": f"{type(err).__name__}: {err}"}), flush=True)

        await hass.async_stop()

    resolver_patch.stop()
    await gateway.stop()


if __name__ == "__main__":
    asyncio.run(run())
