# Elero Gateway HTTP Requests

Part of the [Elero API knowledge](elero-api-knowledge.md) documentation.

All requests are unauthenticated HTTP `GET` requests against port `80` of the
gateway. Successful responses carry an `XC_SUC` key; the payload type
varies per request.
Although the responses it produce do all seem to contain well-formed `json` 
the gateways web server does not set the `content-type` header to indicate 
that. Instead it is always set to `text/html` 

> [!NOTE]
> The endpoints and parameters documented here are based on observed
> gateway traffic and experiments, not on official vendor documentation.

## Get gateway information

```
GET http://<gateway-ip>/info
```

Returns hardware, firmware, and network details of the gateway.

```json
{
  "XC_SUC": {
    "name": "CenteroHome",
    "mhv": "XN I-2M",
    "mfv": "1.2.0-1ff5c7d6",
    "msv": "1.1.32",
    "hwv": "E6",
    "ip": "192.168.0.10",
    "mac": "40-66-7a-xx-xx-xx",
    "start": 1780493307,
    "time": 1780775245,
    "server": "ccs.centero-elero.de:80"
  }
}
```

> [!NOTE] (Response shortened; it also contains network, serial, and session
> details.)

## Get cached device states

```
GET http://<gateway-ip>/cmd?XC_FNC=GetStates
```

Returns the gateway's *cached* state of every known device. `ER` entries
are the cover motors; `EVENT` and `STIMER` entries belong to the gateway's
own automation logic.

```json
{
  "XC_SUC": [
    { "type": "ER", "sid": "01", "adr": "03", "state": "1001", "ts": { "m": "6A244414" } },
    { "type": "ER", "sid": "07", "adr": "06", "state": "1002", "ts": { "m": "6A2436BA" } },
    { "type": "EVENT", "adr": "08", "state": "1" },
    { "type": "STIMER", "sid": "06", "adr": "01", "config": "0000012C", "state": "00:0000012C" }
  ]
}
```

See [cover status codes](elero-status-codes.md) for the meaning of the
`state` values and the [knowledge document](elero-api-knowledge.md) for the
`ts` semantics. Note that this cache is **not** updated for movements the
gateway did not command itself.

## Get gateway configuration

```
GET http://<gateway-ip>/cmd?XC_FNC=GetAll
```

Returns the gateway's automation configuration as a list of `GROUP`,
`ACTION`, `TASK`, and `ASTRO` records.

```json
{
  "XC_SUC": [
    { "sys": "GROUP", "id": "08", "active": "1", "triggerids": "0D", "actionids": "06" },
    { "sys": "ACTION", "id": "01", "type": "ER", "code": "0209", "rf": "00", "ir": "00" },
    { "sys": "TASK", "id": "07", "days": "0000001", "time": "08:00", "dateStart": "2000-00-00", "dateEnd": "2000-00-00" },
    { "sys": "ASTRO", "id": "04", "days": "1111111", "time": "2", "delay": "000A", "t": "", "l": "" }
  ]
}
```

## Send a command to a cover

```
GET http://<gateway-ip>/cmd?XC_FNC=SendSC&type=ER&data=<adr><cmd>
```

`data` is the concatenation of the two-digit hex device address and the
two-digit command code:

| Command code | Action                           |
| ------------ | -------------------------------- |
| `00`         | down / close                     |
| `01`         | up / open                        |
| `02`         | stop                             |
| `0A`         | vent position                    |
| `0B`         | favorite position                |
| `19`         | up / open (silent/quiet mode)    |
| `1A`         | down / close (silent/quiet mode) |

> [!NOTE]
> Silent command codes (`19`, `1A`) enable a slower, quieter travel mode on
> motors that support it. Sending them to a motor without silent support
> results in a harmless no-op: the motor simply ignores the quiet flag and
> moves at its normal speed.

Example - close the cover with address `08`:


```
GET http://<gateway-ip>/cmd?XC_FNC=SendSC&type=ER&data=0800
```

The response carries no payload:

```json
{ "XC_SUC": {} }
```

## Refresh a single cover state

```
GET http://<gateway-ip>/cmd?XC_FNC=RefreshSC&type=ER&adr=<adr>
```

Makes the gateway radio-query the motor and returns the fresh state. This
is the only way to learn about movements the gateway did not command
itself (e.g. via a physical remote).

Example - refresh the cover with address `05`:

```
GET http://<gateway-ip>/cmd?XC_FNC=RefreshSC&type=ER&adr=05
```

```json
{
  "XC_SUC": {
    "type": "ER",
    "sid": "02",
    "adr": "05",
    "state": "1004",
    "ts": { "a": "6A529E68" }
  }
}
```

The radio query completes synchronously; the HTTP round trip typically
finishes in well under a second, while the elero protocol guarantees a
motor answer within 4 seconds.

> [!NOTE]
> The synchronous live-query behavior and the timing were determined
> experimentally, not taken from official vendor documentation.
