# Centero Home Assistant Integration

Home Assistant integration for Elero covers managed through a Centero Home
gateway.

> [!IMPORTANT]
> **This project is not affiliated with, endorsed by, or officially supported by Elero.**
> It is an independent integration developed to work with Elero equipment through the Centero Home gateway.
> Elero and all related product names are trademarks of their respective owners.

## Features

- Automatic discovery of Elero covers connected to the gateway
- Cover control: open / close / stop / move to position
- Services for
  - Move to saved vent position
  - Move to saved favorite position
- Position estimation based on movement time
  - The gateway only reports open / closed / partially open; the
    integration estimates the exact position from how long a cover has
    been moving
  - Configured per cover through two `number` entities ("Time open" and
    "Time close"), adjustable at runtime without a restart and restored
    after restarts
  - The estimate re-calibrates automatically whenever the gateway confirms
    a fully open or fully closed position
  - Once both drive times are set, covers also gain go-to-position support
    (`cover.set_cover_position` and the position slider). The gateway has
    no native positioning command, so the integration starts the motor and
    issues a timed stop when the estimate reaches the target; targets of
    0 % / 100 % always drive fully to the end stops and re-calibrate the
    estimate
  - Covers stopped at the motor's favorite or vent preset report the
    position configured through the per-cover "Position favorite" /
    "Position vent" `number` entities (or the tracked estimate / a 50 %
    fallback when unset) instead of an unknown position
- Detection of externally triggered movements
  - Covers moved via physical remotes are invisible to the gateway on its
    own; the integration actively radio-queries one cover per update cycle
    to pick these movements up
- "Silent drive" for cover movements where the motor supports it. 
- Adaptive polling: 5 s when idle, 1 s while covers are moving

## Installation

### HACS

1. Add this repository as a custom repository in HACS by clicking the button below.
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=riptide94&repository=homeassistant-CenteroHome&category=integration)

2. Select category "Integration".
3. Install.
4. Restart Home Assistant.
5. Add the integration via Settings → Devices & Services.
6. Enter the IP address of your Centero Home Gateway.
7. Done - the integration automatically detects your covers and will add them as devices.

## Configuration

Each cover exposes multiple configuration entities on its device page.

- `number` entities 
  - **Time open** - seconds the cover needs from fully closed to fully open
  - **Time close** - seconds the cover needs from fully open to fully closed

> Measure both once (they usually differ) and enter the values. Position
> estimation stays disabled until both values are set, as is go-to-position
> support (the position slider only appears once both times are set); the
> cover then still works with the coarse open / closed / partial reporting.

> [!NOTE]
> A timed positioning run does not survive a Home Assistant restart: the
> cover finishes at its end stop and the estimate re-calibrates there.

  - **Position favorite** / **Position vent** - where the motor's favorite
    (intermediate) and vent (tilt) presets sit, in % open (100 = fully
    open). When the gateway reports that a cover stopped at one of these
    presets, the integration reports the configured value as the current
    position.

> These values only tell the integration where your presets are - they do
> not program the presets in the motor. When left unset, the integration
> keeps the position tracked during the move instead (or falls back to 50 %
> when no estimate is available).

- `switch` entities
  - **Silent drive** - tells the integration to send the "silent drive" commands to the motor for this cover, which means the cover will move slower and therfore make less noise.

> Enabling this for a drive that does not support "silent drive" has no effect.

> [!NOTE]
> Covers that do support "silent drive" will always use it when the `vent` or `favorite` services are used on them.

> [!NOTE]
> Timed positioning uses the silent commands too, and silent drive moves
> slower. If you use silent drive, measure **Time open** / **Time close**
> with it enabled - otherwise position estimates and timed stops will be
> off.

## Diagnostic Entities

Each cover also exposes two `sensor` entities reflecting the raw status last
received from the gateway. They are disabled by default since they are
mainly intended for debugging; enable them from the entity's settings on the
device page if you need them.

- **State Code** - the raw state code reported by the gateway (e.g. `100A`)
- **State Translation** - a human-readable translation of that code (e.g.
  `opening`)

## Supported hardware

The integration was tested with the following hardware:

- CenteroHome E6 (v1.1.32)
- [Elero RolTop-M-868](https://www.elero.com/en/products/electrical-drives/roltop-m-868)
- [Elero RolMotion M-868](https://www.elero.com/en/products/electrical-drives/rolmotion-m-868)

Other versions of the gateway may work too but were not tested.

## Documentation

Reverse-engineered knowledge about the gateway API and the elero radio
protocol is documented in [doc/elero-api-knowledge.md](doc/elero-api-knowledge.md).

## Development

Tests run against a real Home Assistant core via
[pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component),
which requires a recent Python. The easiest way to get one is
[uv](https://docs.astral.sh/uv/):

```bash
uv venv --python 3.14 .venv
uv pip install --python .venv -r requirements_test.txt
.venv/bin/python -m pytest
```

## Releasing

1. Bump `version` in `custom_components/centero/manifest.json`.
2. Merge to `main`.
3. `git tag vX.Y.Z && git push origin vX.Y.Z`
   — CI verifies the manifest matches the tag and creates a draft release
   with auto-generated notes. It fails if the manifest was not bumped or
   the tag is not on `main`.
4. Review/edit the draft release notes on GitHub and publish.
