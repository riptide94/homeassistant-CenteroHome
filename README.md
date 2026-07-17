# Centero Home Assistant Integration

Home Assistant integration for Elero covers managed through a Centero Home
gateway.

> [!IMPORTANT]
> **This project is not affiliated with, endorsed by, or officially supported by Elero.**
> It is an independent, community-driven integration developed to work with Elero equipment through the Centero Home gateway.
> Elero and all related product names are trademarks of their respective owners.

## Features

- Automatic discovery of Elero covers connected to the gateway
- Cover control: open / close / stop
- Services for
  - Vent position
  - Favorite position
- Position estimation based on movement time
  - The gateway only reports open / closed / partially open; the
    integration estimates the exact position from how long a cover has
    been moving
  - Configured per cover through two `number` entities ("Open time" and
    "Close time"), adjustable at runtime without a restart and restored
    after restarts
  - The estimate re-calibrates automatically whenever the gateway confirms
    a fully open or fully closed position
  - Covers stopped at the motor's favorite or vent preset report the
    position configured through the per-cover "Favorite position" /
    "Vent position" `number` entities (or the tracked estimate / a 50 %
    fallback when unset) instead of an unknown position
- Detection of externally triggered movements
  - Covers moved via physical remotes are invisible to the gateway on its
    own; the integration actively radio-queries one cover per update cycle
    to pick these movements up
- "Silent drive" for cover movements where the motor supports it. 
- Adaptive polling: 5 s when idle, 1 s while covers are moving

## Installation

### HACS

1. Open HACS.
2. Add this repository as a custom repository.
3. Select category "Integration".
4. Install.
5. Restart Home Assistant.
6. Add the integration via Settings → Devices & Services.
7. Enter the IP address of your Centero Home Gateway.

## Configuration

Each cover exposes multiple configuration entities on its device page.

- `number` entities 
  - **Open time** - seconds the cover needs from fully closed to fully open
  - **Close time** - seconds the cover needs from fully open to fully closed

> Measure both once (they usually differ) and enter the values. Position
> estimation stays disabled until both values are set; the cover then still
> works with the coarse open / closed / partial reporting.

  - **Favorite position** / **Vent position** - where the motor's favorite
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
