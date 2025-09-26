# Mi Smart Kettle Pro
![Product](https://raw.githubusercontent.com/asruda/mi_kettle_pro/master/pictures/mi_kettle_pro.png)

This custom component for [Home Assistant](https://www.home-assistant.io) controls the **Mi Smart Kettle Pro**. It uses Bluetooth to connect to the device, same as the Xiaomi Home app.

## Functionality
- Set the temperature of mode: heating, warming
- Heat the water to the set temperature 
- Keep water warm according to the set temperature 
- monitor water temperature, device status

## Supported Models
- yunmi.kettle.v9
- yunmi.kettle.v10 to v16 (likely supported)

yunmi.kettle.v9 was used as the testing device. Other models are likely supported since they all share the **Mi Smart Kettle Pro** name. You can verify device name [here](https://home.miot-spec.com/s/yunmi.kettle.v10).

## Preparation

1. Make sure your **Xiaomi Home app** can control your device.
2. Get your device **token**, **model**, and **MAC address** by following this project: [Xiaomi-cloud-tokens-extractor](https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor).
3. Check that your kettle model is in the range yunmi.kettle.v9 to v16.
4. Make sure your Home Assistant has at least one available Bluetooth adapter which supports BLE 4.2+.
5. It is recommended to enable `Remember keep warm temperature after lifting kettle` in the Xiaomi Home app. The kettle will automatically enter keep-warm status when lifted and placed back.

## Installation

### 1. Install using [HACS](https://hacs.xyz/)
Coming soon.
<!-- **Click**

[![Open your Home Assistant instance and open the Mi Smart Kettle Pro integration inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=asruda&repository=mi_kettle_pro&category=integration)

Then, Open HACS > Search `Mi Smart Kettle Pro` and click **DOWNLOAD**  -->

### 2. Clone and Run Install Script

```bash
cd /tmp
git clone https://github.com/asruda/mi_kettle_pro.git
cd mi_kettle_pro
./install.sh <your HA directory>/config
```

### 3: Download [Releases](https://github.com/asruda/mi_kettle_pro/releases) and Copy Manually

copy `mi_kettle_pro/custom_components/xiaomi_home` folder to `<HA Directory>/config/custom_components` folder in your Home Assistant.

## Configuration

Add a new entry for one device in the Home Assistant UI:
- **Set Heating Temperature**: The target temperature when the `Heat` button is pressed.
- **Set keep-warm Temperature**: The target temperature when the `Keep warm` button is pressed.

## Entities
| Name | Type | Usage | Description |
|----------------------|------|-------|-------------|
| Heat | button | set Heating mode | When the button is pressed, the kettle is set to heating mode first. After the water temperature reaches the target, the kettle switches to keep-warm mode |
| Set Heating Temperature | number | set heating temperature | min: 50, max: 100 |
| Keep warm | button | set keep-warm mode | |
| Set keep-warm Temperature | number | set keep-warm temperature | min: 10, max: 90 |
| Operational Mode | sensor | whether the device can be operated | value: control/monitor |
| Current Temperature | sensor | current water temperature | |
| Status | sensor | kettle status | value: **cooling, heating, keeping warm, idle** |

## Instructions
1. Make sure there is **enough water** in the kettle.
2. Remote control is only possible by pressing the kettle's boil physical button (requires enabling `Automatic heat preservation after boiling` in the Xiaomi Home app), or by pressing the second physical keep-warm button to set in the warming mode. If the device status is idle, the component cannot control the kettle.
3. Only one application can control your device at a time - either this component or the Xiaomi Home app. If you want to control your device using the Xiaomi Home app, please disable the device in Home Assistant first.
4. When the login process finishes, the component will update mode config `3` and `4` on your device as follows:

| Mode | Edit | Description |
|------|------|-------------|
| `0` | no | - |
| `1` | no | - |
| `2` | no | - |
| `3` | **yes** | warming mode, Temperature: `warming temperature`, Duration: 12 hours |
| `4` | **yes** | heating mode, Temperature: `heating temperature`, Duration: 12 hours |

## Troubleshooting
1. If the connection is intermittent, try lifting and replacing the kettle.

## UUID Characteristics

| UUID | Usage | Data Index Explanation | Description |
|------|-------|-------------------| ------------|
|aa05 | set config  |	`0`: Remember keep warm temperature after lifting kettle,01:enable||
|aa02 | get status | `0`: kettle status, 00: idle, 01: heating, 02: heating, 03: warming, 04: cooling <br> `4`: mode<br>`5`: current temperature<br>`6`: Automatic heat preservation after boiling, 01:enable, 00:disable<br>`7`: Keep Warm Time Elapsed<br>`10`: Remember keep warm temperature after lifting kettle, 01:enable, 00:disable|`mode` values range from 0 to 4, its configuration uses UUID `aa01`|
|aa01 | set mode | `0`: mode<br>`1`: Automatic heat preservation after boiling, 01:enable, 00:disable||
|aa03 | read mode config | mode configuration [0-4]: <br>`0`: target temperature of mode index 0<br> `1`: keep warm duration of mode index 0<br>...<br>`8`: target temperature of mode index 4<br>`9`: keep warm duration of mode index 4|`keep warm duration` value 18 indicates 12hours, value 17 indicates 11.5hours|
|aa04 | set mode config | same format as `aa03`
