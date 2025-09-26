"""Constants for the Mi Kettle Pro integration."""

from typing import Final
from homeassistant.const import UnitOfTemperature

DOMAIN: Final = "mi_kettle_pro"

# Configuration keys
CONF_MAC: Final = "mac"
CONF_DEVICE_TOKEN: Final = "device_token"
CONF_DEVICE_NAME: Final = "device_name"
CONF_POLL_INTERVAL: Final = "poll_interval"
CONF_TEMPERATURE_UNIT: Final = "temperature_unit"
CONF_BT_INTERFACE: Final = "bt_interface"
CONF_HEAT_TEMPERATURE: Final = "heat_temperature"
CONF_WARM_TEMPERATURE: Final = "warm_temperature"
CONF_DEVICE_MODEL: Final = "device_model"
CONNECTION_TYPE: Final = "connection_type"


# Default values
DEFAULT_POLL_INTERVAL: Final = 30  # seconds
DEFAULT_TEMPERATURE_UNIT: Final = UnitOfTemperature.CELSIUS
DEFAULT_DEVICE_MODEL: Final = ""
DEFAULT_DEVICE_NAME: Final = "Mi Kettle Pro"

# Supported temperature units
TEMPERATURE_UNITS: Final = [
    UnitOfTemperature.CELSIUS,
    UnitOfTemperature.FAHRENHEIT
]

# Device capabilities
CAPABILITIES: Final = {
    "status": True,
    "current_temperature": True,
    "heat_temperature": True,
    "warm_temperature": True,
    "auto_keep_warm": True,
    "controllable": True
}

# Bluetooth service and characteristic UUIDs
SERVICE_AUTH: Final = "0000fe95-0000-1000-8000-00805f9b34fb"
SERVICE_BIZ: Final = "01344736-0000-1000-8000-262837236156"

UUID_AUTH_INIT: Final = "00000010-0000-1000-8000-00805f9b34fb"
UUID_AUTH: Final = "00000019-0000-1000-8000-00805f9b34fb"
UUID_WARM_SETTING_1: Final = "0000aa01-0000-1000-8000-00805f9b34fb"
UUID_WARM_SETTING_2: Final = "0000aa05-0000-1000-8000-00805f9b34fb"
UUID_WARM_STATUS: Final = "0000aa02-0000-1000-8000-00805f9b34fb"
UUID_READ_MODE_CONFIG: Final = "0000aa03-0000-1000-8000-00805f9b34fb"
UUID_WRITE_MODE_CONFIG: Final = "0000aa04-0000-1000-8000-00805f9b34fb"

# Auth Protocol constants
OP_AUTH_INIT_1: Final = bytes.fromhex("a4")
OP_AUTH_INIT_2: Final = bytes.fromhex("24000000")
OP_PREPARE_RAND: Final = bytes.fromhex("0000000b0100")
OP_PREPARE_TOKEN: Final = bytes.fromhex("0000000a0200")
OP_SUCCESS: Final = bytes.fromhex("21000000")
OP_ALREADY_LOGIN: Final = bytes.fromhex("e2000000")
OP_DEV_PREPARE_RAND: Final = bytes.fromhex("0000000d0100")
OP_DEV_PREPARE_TOKEN: Final = bytes.fromhex("0000000c0200")
ACK_READY: Final = bytes.fromhex("00000101")
ACK_SUCCESS: Final = bytes.fromhex("00000100")

# Status mapping
MI_ACTION_MAP: Final = {
    0: "idle",
    1: "heating",
    2: "heating",  # Heat And Keep Warm To The Set Temperature
    3: "keeping warm",
    4: "cooling",
}

# Status mapping
CUSTOME_MODE_ACTION_MAP: Final = {
    0: "Warming",
    3: "Warming",
    4: "Heating",
}

MI_BOOL_MAP: Final = {
    0: "no",
    1: "yes"
}

# Temperature settings
DEFAULT_HEAT_TEMPERATURE: Final = 90  # Default heat temperature
MIN_HEAT_TEMPERATURE: Final = 50      # Minimum heat temperature
MAX_HEAT_TEMPERATURE: Final = 100     # Maximum heat temperature

DEFAULT_WARM_TEMPERATURE: Final = 20  # Default warm temperature
MIN_WARM_TEMPERATURE: Final = 10      # Minimum warm temperature
MAX_WARM_TEMPERATURE: Final = 90      # Maximum warm temperature

# Event Listen
AVAIL_EVENT = f"{DOMAIN}_availability_changed"
AVAIL_EVENT_KEY_ENTRY_ID = "entry_id"
AVAIL_EVENT_KEY_AVAIL = "available"
AVAIL_EVENT_KEY_IS_LOGIN = "is_login"
AVAIL_EVENT_KEY_IS_CONTROL = "is_control"

# device_mode
WARM_INDEX = 3
HEAT_INDEX = 4
MODE_LENGTH = 4
