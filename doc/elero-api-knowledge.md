# Elero API Knowledge

Entry point for everything known about the Centero Home gateway and the
elero radio protocol.

> [!NOTE] Information in this document was mostly gathered through reverse engineering and may not be 100% accurate!

## Documents

- [Gateway HTTP requests](elero-gateway-requests.md) - all discovered
  endpoints with usage and response examples
- [Cover status codes](elero-status-codes.md) - decoded ER status codes and
  how the integration handles them

## The gateway

The Centero Home gateway appears to be a rebranded mediola AIO gateway,
recognizable by the `XC_FNC` / `XC_SUC` HTTP protocol and the
`ccs.centero-elero.de` cloud server in its `/info` response. General
documentation for mediola AIO gateways largely applies.

The HTTP API consists of plain unauthenticated GET requests on port 80.

> [!NOTE]
> The mediola relationship is inferred from protocol observation, not
> confirmed by official vendor documentation.

## The radio protocol

Elero motors communicate bidirectionally on 868 MHz, but the protocol seems to be
poll-based: motors do **not** broadcast movements on their own. A
transmitter (gateway, remote, USB stick) has to query a motor to learn its
state.

Consequences for the gateway:

- Movements the gateway did not command itself are not noticed by it. A
  cover moved with a physical remote never updates in `GetStates`.
- `RefreshSC` must be used which makes the gateway radio-query a 
single motor synchronously and returns the fresh state.

> [!NOTE]
> The gateway behavior described above is based on experiments against
> real hardware, not on official vendor documentation.

The integration therefore radio-queries one cover per update cycle:
externally-moving covers with priority, idle covers round-robin, and no
queries at all while HA-commanded movement is in progress (the gateway
tracks its own commands).

## `ts` timestamps

The `ts` values in `GetStates` / `RefreshSC` responses are hex-encoded
epoch seconds (`date -u -d @$((16#<hex>))`). They do **not** track state
freshness - a physical move followed by a `RefreshSC` leaves them
unchanged. They most likely record the last command the gateway itself
issued to the motor: `m` = manual (app/HTTP), `a` = automatic (astro/timer
schedules).

> [!NOTE]
> The `m`/`a` interpretation is based on experiments and observed data,
> not on official vendor documentation.

## UDP events

mediola gateways are reported to broadcast state events over UDP - port
1902 (`{XC_EVT}{...}` payloads, v4 generation) or 1901 (`STA:{...}`
payloads, v6 generation) - but on newer generations only when a blind
reaches fully open/closed.

Whether the Centero gateway emits anything has not been confirmed 
yet and the integration relies purely on HTTP polling.
