# Elero Cover Status Codes

Part of the [Elero API knowledge](elero-api-knowledge.md) documentation.

ER device states reported by the gateway are `10` followed by the raw
elero status byte.

| Code   | elero meaning                                       | Integration handling           |
| ------ | --------------------------------------------------- | ------------------------------ |
| `1000` | no information                                      | position unknown               |
| `1001` | top position stop                                   | open, position 100             |
| `1002` | bottom position stop                                | closed, position 0             |
| `1003` | intermediate position stop (favorite preset)        | stationary, position unknown   |
| `1004` | tilt / ventilation position stop (vent preset)      | stationary, position unknown   |
| `1005` | blocking detected                                   | error, keeps last position     |
| `1006` | motor overheated                                    | error, keeps last position     |
| `1007` | timeout / motor did not answer                      | error, keeps last position     |
| `1008` | start to move up                                    | opening                        |
| `1009` | start to move down                                  | closing                        |
| `100A` | moving up                                           | opening                        |
| `100B` | moving down                                         | closing                        |
| `100D` | stopped in undefined position                       | partial, keeps travel estimate |
| `100E` | top position stop, which is the tilt position       | open, position 100             |
| `100F` | bottom position stop, which is the intermediate one | closed, position 0             |
