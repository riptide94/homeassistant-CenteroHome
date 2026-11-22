---
name: run-centero
description: Build, run, and drive the Centero Home Assistant integration (custom_components/centero) against a real Home Assistant core. Use when asked to run/start/test the Centero integration, exercise its cover/number/switch/sensor entities or services, or verify a change actually works end-to-end (not just pytest).
---

`centero` is a Home Assistant custom integration (a plugin loaded into HA
core, not a standalone server) for Elero covers behind a Centero gateway.
There is no GUI in this repo and no `home-assistant-frontend` package
installed, so "running" it means booting a **real**
`homeassistant.core.HomeAssistant` instance with the real integration code
loaded, against a **real** in-process HTTP server that fakes the physical
gateway's tiny JSON API (there's no hardware in this container). Drive it
via `.claude/skills/run-centero/driver.py` — an interactive REPL that reads
newline-delimited commands from stdin and prints one JSON object per line.
This exercises strictly more of the integration than the pytest suite
does: the pytest fixtures patch `CenteroAPI` out entirely, while the
driver's fake gateway is hit over a real `aiohttp` HTTP connection, so the
integration's real network code runs too.

All paths below are relative to the repo root.

## Prerequisites

Runtime is Python 3.14, managed with `uv`. No OS packages needed — this
container already has `uv` at `~/.local/bin/uv`.

## Setup

A `.venv` already exists at repo root with everything installed. To build
one from scratch (verified working in this container):

```bash
uv venv --python 3.14 .venv
uv pip install --python .venv -r requirements_test.txt
```

## Build

No build step — pure Python, loaded by Home Assistant directly from
`custom_components/centero/`.

## Run (agent path)

Launch the driver and pipe it commands. It boots HA, loads `centero`
pointed at the fake gateway, and prints a `{"event": "ready", ...}` line
once the config entry is set up and entities exist — wait for that line
before sending further commands.

```bash
.venv/bin/python .claude/skills/run-centero/driver.py <<'EOF'
states
call cover open_cover cover.elero_sid01_adr03
gw-set 03 1001
refresh
state cover.elero_sid01_adr03
quit
EOF
```

Verified output (trimmed) for that exact session:

```
{"event": "ready", "setup_ok": true, "gateway_port": 35359, "entities": [...]}
[{"entity_id": "cover.elero_sid01_adr03", "state": "closed", ...}, ...]
{"called": ["cover", "open_cover", {"entity_id": "cover.elero_sid01_adr03"}], "result": {...}}
{"ok": true, "devices": {"03": {"sid": "01", "state": "1001"}}}
{"ok": true}
{"entity_id": "cover.elero_sid01_adr03", "state": "open", "attributes": {"current_position": 100, ...}}
```

The fake gateway starts with one ER device: `sid=01 adr=03`, state
`STATE_CLOSED` (`1002`) — same defaults as `tests/common.py`, so entity
IDs match what the pytest suite uses (`cover.elero_sid01_adr03`, etc.).

| command | what it does |
|---|---|
| `states` | dump every entity's state + attributes |
| `state <entity_id>` | dump one entity |
| `call <domain> <service> <entity_id> [k=v ...]` | call a HA service; `v` is parsed as JSON (`12.5`, `true`, `"x"`) with a raw-string fallback |
| `gw-devices` | dump the fake gateway's devices + every `SendSC` command it has received |
| `gw-set <adr> <state_code>` | change what the gateway reports for a device (simulates the motor finishing a move, or a physical remote) |
| `gw-add <sid> <adr> <state_code>` | add another fake ER device |
| `refresh` | run one coordinator poll cycle (`coordinator.async_refresh()`) |
| `sleep <seconds>` | `await asyncio.sleep(seconds)` |
| `quit` / `exit` | clean shutdown (stops HA, closes the fake gateway) |

State codes live in `custom_components/centero/const.py` (`STATE_OPEN =
"1001"`, `STATE_CLOSED = "1002"`, `STATE_INTERMEDIATE = "1003"`,
`STATE_VENT = "1004"`, `STATE_OPENING = "100A"`, `STATE_CLOSING =
"100B"`, `STATE_PARTIAL = "100D"`, ...). Command codes seen in
`gw-devices` → `sent_commands`: `00` down, `01` up, `02` stop, `0A` vent,
`0B` favorite, `1A`/`19` silent down/up.

### Go-to-position (`cover.set_cover_position`)

Only available once **both** drive times are set — `supported_features`
goes from `11` to `15` the moment the second `number` is set. The
integration starts the motor and fires a timed `02` (stop) when the
estimate reaches the target. The fake gateway does not simulate motion,
so set the moving code yourself *before* calling the service, otherwise
the debounced refresh that follows the call sees a stopped state and
(correctly) cancels the pending stop:

```bash
.venv/bin/python .claude/skills/run-centero/driver.py <<'EOF'
call number set_value number.elero_sid01_adr03_time_open value=4
call number set_value number.elero_sid01_adr03_time_close value=6
gw-set 03 100A
call cover set_cover_position cover.elero_sid01_adr03 position=50
sleep 2.5
gw-devices
gw-set 03 100D
refresh
state cover.elero_sid01_adr03
quit
EOF
```

Verified: `sent_commands` is `[["03","01"],["03","02"]]` (up, then stop
after ~2s = 50 % of 4s) and the cover ends at `current_position: 50`.
Going down works the same with `gw-set 03 100B` and `time_close`.

**Custom services are registered under the `centero` domain, not
`cover`** — call them as `call centero vent <entity_id>` / `call centero
favorite <entity_id>`, not `call cover vent ...`.

## Run (human path)

There isn't one in this container — no frontend package is installed
(`pip list | grep frontend` is empty), so there's nothing to click. The
driver above is the only way to exercise this integration here.

## Test

```bash
.venv/bin/python -m pytest -q
```

61 passed in ~2s, no network access needed (`CenteroAPI` is patched out
in these tests — see `tests/conftest.py`).

## Gotchas

- **`async_get_clientsession(hass)` reaches into zeroconf/network.** HA's
  real aiohttp client-session helper builds a DNS resolver via the
  `network`/`zeroconf` components' `hass.data`. Neither is loaded here (only
  `centero` is), so it raises `KeyError: 'network'`. Fix: patch
  `homeassistant.helpers.aiohttp_client._async_make_resolver` to return a
  plain `aiohttp.resolver.AsyncResolver()` — this is exactly what
  `pytest-homeassistant-custom-component`'s own `mock_zeroconf_resolver`
  fixture does; the driver replicates it. Without the `resolver.real_close
  = resolver.close` line, HA's shutdown path throws `AttributeError:
  'AsyncResolver' object has no attribute 'real_close'` on `async_stop()`
  (harmless but noisy — the driver sets it to keep shutdown clean).
- **`update_coordinator.DataUpdateCoordinator.__init__` needs the frame
  helper set up**, or it raises `RuntimeError: Frame helper not set up`
  the moment `CenteroCoordinator()` is constructed. Call
  `homeassistant.helpers.frame.async_setup(hass)` right after creating
  `hass`, before setting up the config entry. Pytest gets this for free
  from its own fixtures; a bare `async_test_home_assistant()` does not.
- **`enable_custom_integrations` isn't automatic outside pytest.** By
  default `HomeAssistant.loader` refuses to see anything under
  `custom_components/` in test-style config dirs. Replicate the pytest
  fixture manually: `hass.data.pop(loader.DATA_CUSTOM_COMPONENTS, None)`
  right after the `HomeAssistant` object is created.
- **`vent`/`favorite` are entity services on the `centero` domain**, set up
  via `platform.async_register_entity_service` in `cover.py`. Calling
  `cover.vent` (guessing by analogy with `cover.open_cover`) 404s with
  `ServiceNotFound`; the actual call is `centero.vent`.
- **Position-tracking presets need two steps to see the payoff:** setting
  `number.<...>_position_favorite` alone does nothing to `cover.*`'s
  reported position until the gateway is *also* reported as sitting at
  that preset (`gw-set <adr> 1003` then `refresh`). This mirrors the
  actual v0.2.1 feature (position is reported only once the gateway
  confirms the cover stopped at the preset).
- **The diagnostic `sensor` entities don't appear in the `ready` entity
  list.** They are `EntityCategory.DIAGNOSTIC` with
  `entity_registry_enabled_default = False`, so HA registers them
  disabled. The raw gateway code is still visible on the cover itself via
  the `centero_state` / `centero_state_name` attributes.
- **A stopped-state `gw-set` + `refresh` during a timed set-position run
  cancels the pending stop** — that's the intended handling of a cover
  reaching an end stop / being stopped by a remote, not a bug. Only
  `gw-set` a stopped code after the `02` shows up in `gw-devices`.

## Troubleshooting

- **`RuntimeError: Frame helper not set up`** when the config entry is set
  up: missing `frame.async_setup(hass)` — see Gotchas.
- **`KeyError: 'network'`** deep in `async_setup_entry` → `async_get_clientsession`:
  missing the `_async_make_resolver` patch — see Gotchas.
- **`ServiceNotFound: service_not_found`** calling `vent`/`favorite`:
  you called them under `cover.*` instead of `centero.*`.
- **`We found a custom integration centero which has not been tested by
  Home Assistant` on stderr**: expected and harmless — HA prints this for
  every custom component; it is not an error.
