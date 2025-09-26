## UUID Characteristics

| UUID | Usage | Data Index Explanation | Description |
|------|-------|-------------------| ------------|
|aa05 | set config  |	`0`: Remember keep warm temperature after lifting kettle,01:enable||
|aa02 | get status | `0`: kettle status, 00: idle, 01: heating, 02: heating, 03: warming, 04: cooling <br> `4`: mode<br>`5`: current temperature<br>`6`: Automatic heat preservation after boiling, 01:enable, 00:disable<br>`7`: Keep Warm Time Elapsed<br>`10`: Remember keep warm temperature after lifting kettle, 01:enable, 00:disable|`mode` values range from 0 to 4, its configuration uses UUID `aa01`|
|aa01 | set mode | `0`: mode<br>`1`: Automatic heat preservation after boiling, 01:enable, 00:disable||
|aa03 | read mode config | mode configuration [0-4]: <br>`0`: target temperature of mode index 0<br> `1`: keep warm duration of mode index 0<br>...<br>`8`: target temperature of mode index 4<br>`9`: keep warm duration of mode index 4|`keep warm duration` value 18 indicates 12hours, value 17 indicates 11.5hours|
|aa04 | set mode config | same format as `aa03`