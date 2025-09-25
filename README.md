# Mi Kettle Pro
![Product](https://raw.githubusercontent.com/asruda/mi_kettle_pro/pictures/mi_kettle_pro.png)

This custom component for [Home Assistant](https://www.home-assistant.io) controls the **Mi Smart Kettle Pro**. This component uses Bluetooth to connect to the device, same as the Xiaomi Home app.

## Functionality
- Set the temperature of mode: heat, warm
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
4. Make sure your Home Assistant has at least one available Bluetooth adapter which supports BLE 4.2.
5. It is recommended to enable `Remember keep warm temperature after lifting kettle` in the Xiaomi Home app. The kettle will automatically enter keep-warm status when lifted and placed back.

## Installation

### HACS

Coming soon.

### Manual

1. Copy the `mi_kettle_pro` folder to your `custom_components` directory
2. Restart Home Assistant

## Configuration

Add a new entry for one device in the Home Assistant UI:
- **Set Heating Temperature**: The target temperature when the `Heat` button is pressed.
- **Set keep-warm Temperature**: The target temperature when the `Keep warm` button is pressed.

## Entities
| Name | Type | Usage | Description |
|------|------|-------|-------------|
| Heat | button | set Heating mode | When the button is pressed, the kettle is set to heating mode first. After the water temperature reaches the target, the kettle switches to keep-warm mode |
| Set Heating Temperature | number | set heating temperature | min: 50, max: 100 |
| Keep warm | button | set keep-warm mode | |
| Set keep-warm Temperature | number | set keep-warm temperature | min: 10, max: 90 |
| Operational Mode | sensor | whether the device can be operated | value: control/monitor |
| Current Temperature | sensor | current water temperature | |
| Status | sensor | kettle status | value: **cooling, heating, keeping warm, idle** |

## Instructions
1. Make sure there is **enough water** in the kettle.
2. Remote control is only possible by pressing the kettle's boil physical button (requires enabling `Automatic heat preservation after boiling` in the Xiaomi Home app), or by pressing the second physical keep-warm button to set the keep-warm status. If the device status is idle, the component cannot change the kettle's mode.
3. Only one application can control your device at a time - either this component or the Xiaomi Home app. If you want to control your device using the Xiaomi Home app, please disable the device in Home Assistant first.
4. After the login step, the component will modify profiles 4 and 5 on your device as follows:

| Mode | Edit | Description |
|------|------|-------------|
| `0` | no | - |
| `1` | no | - |
| `2` | no | - |
| `3` | **yes** | warming mode, Temperature: `warming temperature`, Duration: 12 hours |
| `4` | **yes** | heating mode, Temperature: `heating temperature`, Duration: 12 hours |

## Troubleshooting

## 