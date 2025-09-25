"""Device configuration mapping for MiKettle Pro integration."""

from typing import TypedDict

class DeviceEntityConfig(TypedDict):
    """Configuration for a single entity."""
    entity_type: str  # sensor, switch, button, number, etc.
    entity_id: str
    name: str
    device_class: str | None
    icon: str | None
    unit_of_measurement: str | None

class DeviceConfig(TypedDict):
    """Configuration for a device type."""
    name: str
    support_models: list[str]
    manufacturer: str
    entities: list[DeviceEntityConfig]

# 设备配置映射表
DEVICE_CONFIGS: dict[str, DeviceConfig] = {
    "mi_kettle_pro": {
        "name": "Mi Kettle Pro",
        "support_models": [
            "MiKetv9",
            "MiKetv10",
            "MiKetv11",
            "MiKetv12",
            "MiKetv13",
            "MiKetv14",
            "MiKetv15",
            "MiKetv16",
        ],
        "manufacturer": "Xiaomi",
        "entities": {
            "button": ["MiKettleProBoilButton", "MiKettleProWarmButton"],
            "number": [
                "MiKettleProBoilTemperatureNumber",
                "MiKettleProWarmTemperatureNumber"
            ],
            "sensor": [
                "MiKettleProStatusSensor",
                "MiKettleProCurrentTemperatureSensor",
                "MiKettleProControllableSensor"
            ],
            "time": [],
            "switch": [],
        }
    },
    "mi_kettle_pro_v2": {
        "name": "Mi Kettle Pro V2",
        "support_models": [],
        "manufacturer": "Xiaomi",
        "entities": {},
    }
}

SUPPORTED_DEVICES = DEVICE_CONFIGS.keys()

def get_device_model(device_name):
    """Get device model by device name."""
    for device_model, device_config in DEVICE_CONFIGS.items():
        if device_name in device_config["support_models"]:
            return device_model
    return None
