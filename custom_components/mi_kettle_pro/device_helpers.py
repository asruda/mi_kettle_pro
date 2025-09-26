"""
The MGMTBluetoothCtl, hci_get_mac, and BT_INTERFACES components in this file are sourced 
from the [ble_monitor] project (https://github.com/custom-components/ble_monitor/blob/master/custom_components/ble_monitor/bt_helpers.py), 
licensed under MIT (https://github.com/custom-components/ble_monitor/blob/master/LICENSE).

Bluetooth helpers for Mi Kettle Pro integration."
"""

from __future__ import annotations

import asyncio
import logging

from bleak import BleakScanner
from btsocket import btmgmt_protocol, btmgmt_sync
from btsocket.btmgmt_socket import BluetoothSocketError
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_DEVICE_MODEL, CONF_MAC, DOMAIN, CONF_BT_INTERFACE
from .device.mikettle_pro import MiKettlePro
from .device_config import SUPPORTED_DEVICES, get_device_model

_LOGGER = logging.getLogger(__name__)


class MiKettleProManager:
    """Manager for Mi Kettle Pro Link connection and data handling."""
    _update_task: None
    _stop_future: None
    device_model: str
    device_parser: None

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        conn_type: str,

    ) -> None:
        """Initialize the Bluetooth manager."""
        self.hass = hass
        self.entry = entry
        self.mac_address = self.entry.data[CONF_MAC]
        self.device_model = self.entry.options.get(CONF_DEVICE_MODEL)
        self.conn_type = conn_type
        if conn_type == "ble":
            self.bt_interface = ""
            self.ble_client = None

    async def async_setup(self) -> bool:
        device_name = await self.async_fetch_device_name()
        if not self.device_model:
            self.device_model = get_device_model(device_name)
        if self.device_model in SUPPORTED_DEVICES:
            # cache device model in options
            new_options = {
                **self.entry.options,
                CONF_DEVICE_MODEL: self.device_model
            }
            self.hass.config_entries.async_update_entry(
                self.entry,
                options=new_options
            )
        else:
            msg = (
                f"Unsupport device, mac: [{self.mac_address}], "
                f"device_name: [{device_name}], device_model: [{self.device_model}]"
            )
            _LOGGER.error(msg)
            raise MiKettleNotSupportException(msg)            

        # store device_model
        self.hass.data[DOMAIN][f"{self.entry.entry_id}_device_model"] = self.device_model

        # Create device instance
        if self.device_model == "mi_kettle_pro":
            _LOGGER.info(
                "Setup device success, mac %s, device_name %s, "
                "use %s as device parser",
                self.mac_address,
                device_name,
                self.device_model
            )
            self.device_parser = MiKettlePro(
                hass=self.hass,
                ble_client=self.ble_client,
                mac_address=self.mac_address,
                device_token=self.entry.data["device_token"],
                poll_interval=self.entry.data.get("poll_interval", 30),
                bt_interface=self.bt_interface,
                entry_id=self.entry.entry_id
            )
        else:
            msg = (
                f"Unsupport device, mac: [{self.mac_address}], "
                f"device_name: [{device_name}]"
            )
            _LOGGER.error(msg)
            raise MiKettleNotSupportException(msg)
        return True

    async def async_start(self) -> None:
        """Start the Bluetooth manager."""
        _LOGGER.info("Starting Mi Kettle Pro Bluetooth manager")
        self._stop_future = self.hass.loop.create_future()
        self.device_parser.loop_active = True
        task_name = f"mikettle_pro_update_loop_{self.mac_address}"
        self._update_task = self.hass.async_create_background_task(
            self.device_parser.async_update_loop(),
            task_name
        )

    async def async_stop(self) -> None:
        """Stop the Bluetooth manager."""
        _LOGGER.info("Stopping Mi Kettle Pro Bluetooth manager")
        if self._stop_future and not self._stop_future.done():
            self._stop_future.set_result(None)
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                # Task cancellation is expected
                pass
        self.device_parser.loop_active = False
        await self.device_parser.async_disconnect()

    async def async_fetch_device_name(self):
        # 获得一个能连接的蓝牙适配器
        interface_list = self.entry.data[CONF_BT_INTERFACE]
        if "disable" in interface_list:
            _LOGGER.info("Bluetooth interface is disabled, device: %s", self.mac_address)
            return False
        for interface in interface_list:
            client = await self.get_ble_client(interface)
            if client:
                self.bt_interface = interface
                self.ble_client = client
                return client.name
            _LOGGER.warning("Unable to connect to device %s, bt_interface %s", 
                            self.mac_address, interface)
        _LOGGER.error("Unable to connect to device %s, bt_interface_list %r", 
                      self.mac_address, interface_list)

    async def get_ble_client(self, bt_interface):
        ble_client = bluetooth.async_ble_device_from_address(
            self.hass, self.mac_address, connectable=True
        )

        if not ble_client:
            advertisement_data = await self.get_advertisement_data(
                adapter=bt_interface
            )
            if not advertisement_data:
                _LOGGER.error(
                    "Failed to get advertisement data for device %s, "
                    "interface %s",
                    self.mac_address,
                    bt_interface
                )
                return False
            _LOGGER.info(
                "Get Device advertisement data, mac: %s, data: %s, "
                "interface: %s",
                self.mac_address,
                advertisement_data,
                bt_interface
            )
            ble_client = bluetooth.async_ble_device_from_address(
                self.hass, self.mac_address, connectable=True
            )

        return ble_client

    async def get_advertisement_data(self, timeout=10, adapter=None):
        """Get device advertisement data"""
        target_mac = self.mac_address.upper()
        advertisement_data = None

        def detection_callback(device, adv_data):
            nonlocal advertisement_data
            if device.address.upper() == target_mac:
                advertisement_data = adv_data

        scanner = BleakScanner(
            detection_callback=detection_callback,
            scanning_mode="active",
            adapter=adapter,
        )

        _LOGGER.debug("Starting advertisement scan for device %s", target_mac)

        try:
            await scanner.start()
            await asyncio.sleep(timeout)
        except (OSError, ConnectionError, TimeoutError) as exc:
            _LOGGER.error("Advertisement scan failed: %s", exc)
            return None
        except Exception as exc:
            _LOGGER.error("Advertisement scan failed unexpected: %s", exc)
            return None
        finally:
            await scanner.stop()

        if advertisement_data:
            return self._parse_advertisement_data(advertisement_data)
        return None

    def _parse_advertisement_data(self, adv_data):
        """Parse advertisement data"""
        if not adv_data:
            return None

        parsed_data = {
            "rssi": adv_data.rssi,
            "local_name": adv_data.local_name,
            "tx_power": adv_data.tx_power,
            "manufacturer_data": {},
            "service_data": {},
            "service_uuids": adv_data.service_uuids or [],
        }

        # Parse manufacturer data
        if adv_data.manufacturer_data:
            for manufacturer_id, data in adv_data.manufacturer_data.items():
                parsed_data["manufacturer_data"][manufacturer_id] = {
                    "hex": data.hex(),
                    "length": len(data),
                    "data": list(data)
                }

        # Parse service data
        if adv_data.service_data:
            for service_uuid, data in adv_data.service_data.items():
                parsed_data["service_data"][service_uuid] = {
                    "hex": data.hex(),
                    "length": len(data),
                    "data": list(data)
                }

        # Special parsing for Xiaomi data (if exists)
        if 0xFE95 in parsed_data["manufacturer_data"]:
            xiaomi_data = self._parse_xiaomi_data(
                parsed_data["manufacturer_data"][0xFE95]["data"]
            )
            parsed_data["xiaomi_data"] = xiaomi_data

        return parsed_data

    def _parse_xiaomi_data(self, data):
        """Parse Xiaomi device manufacturer data"""
        if not data or len(data) < 5:
            return None

        try:
            # Xiaomi advertisement packet format parsing
            frame_control = bytes(data[0:2]).hex() if len(data) >= 2 else None
            product_id = bytes(data[2:4]).hex() if len(data) >= 4 else None
            frame_counter = data[4] if len(data) >= 5 else None
            capability = data[5] if len(data) >= 6 else None

            return {
                "frame_control": frame_control,
                "product_id": product_id,
                "frame_counter": frame_counter,
                "capability": capability,
                "raw_length": len(data)
            }
        except (ValueError, IndexError, TypeError) as exc:
            _LOGGER.warning("Failed to parse Xiaomi data: %s", exc)
            return None

class MGMTBluetoothCtl:
    """Class to control interfaces using the BlueZ management API."""

    def __init__(self, hci=None) -> None:
        self.idx = None
        self.mac = None
        self._hci = hci
        self.presented_list = {}
        idxdata = btmgmt_sync.send("ReadControllerIndexList", None)
        if idxdata.event_frame.status.value != 0x00:  # 0x00 - Success
            _LOGGER.error(
                "Unable to get hci controllers index list! "
                "Event frame status: %s",
                idxdata.event_frame.status,
            )
            return
        if idxdata.cmd_response_frame.num_controllers == 0:
            _LOGGER.warning(
                "There are no BT controllers present in the system!"
            )
            return
        hci_idx_list = getattr(
            idxdata.cmd_response_frame, "controller_index[i]"
        )
        for idx in hci_idx_list:
            hci_info = btmgmt_sync.send("ReadControllerInformation", idx)
            _LOGGER.debug(hci_info)
            # bit 9 == LE capability
            # (https://github.com/bluez/bluez/blob/master/doc/mgmt-api.txt)
            bt_le = bool(
                hci_info.cmd_response_frame.supported_settings
                & 0b000000001000000000
            )
            if bt_le is not True:
                _LOGGER.warning(
                    "hci%i (%s) have no BT LE capabilities and "
                    "will be ignored.",
                    idx,
                    hci_info.cmd_response_frame.address,
                )
                continue
            self.presented_list[idx] = hci_info.cmd_response_frame.address
            if hci == idx:
                self.idx = idx
                self.mac = hci_info.cmd_response_frame.address

    @property
    def powered(self):
        """Powered state of the interface"""
        if self.idx is not None:
            response = btmgmt_sync.send("ReadControllerInformation", self.idx)
            return response.cmd_response_frame.current_settings.get(
                btmgmt_protocol.SupportedSettings.Powered
            )
        return None

    @powered.setter
    def powered(self, new_state):
        response = btmgmt_sync.send(
            "SetPowered", self.idx, int(new_state is True)
        )
        if response.event_frame.status.value == 0x00:  # 0x00 - Success
            return True
        return False


# Bluetooth interfaces available on the system
def hci_get_mac(iface_list=None):
    """Get dict of available bluetooth interfaces, returns hci and mac."""
    # Result example: {0: "F2:67:F3:5B:4D:FC", 1: "00:1A:7D:DA:71:11"}
    try:
        btctl = MGMTBluetoothCtl()
    except BluetoothSocketError as error:
        _LOGGER.debug("BluetoothSocketError: %s", error)
        return {}
    q_iface_list = iface_list or [0]
    btaddress_dict = {}
    for hci_idx in q_iface_list:
        try:
            btaddress_dict[hci_idx] = btctl.presented_list[hci_idx]
        except KeyError:
            pass
    return btaddress_dict


BT_INTERFACES = hci_get_mac([0, 1, 2, 3])
if BT_INTERFACES:
    DEFAULT_BT_INTERFACE = list(BT_INTERFACES.items())[0][1]
    DEFAULT_HCI_INTERFACE = list(BT_INTERFACES.items())[0][0]
    BT_MULTI_SELECT = {
        value: f"{value} (hci{key})"
        for (key, value) in BT_INTERFACES.items()
    }
else:
    DEFAULT_BT_INTERFACE = "disable"
    DEFAULT_HCI_INTERFACE = "disable"
    BT_MULTI_SELECT = {}
    _LOGGER.debug(
        "No Bluetooth LE adapter found. Make sure Bluetooth is installed."
    )
    BT_MULTI_SELECT["disable"] = "Don't use Bluetooth adapter"

class MiKettleNotSupportException(Exception):
    def __init__(self, message="Model Not Support"):
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return f"MiKettleNotSupportException: {self.message}"
