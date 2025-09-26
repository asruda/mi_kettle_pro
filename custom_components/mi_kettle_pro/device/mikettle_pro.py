"""MiKettle Pro specific device implementation."""

import asyncio
import binascii
import logging
import hashlib
import hmac
import os
from collections.abc import Callable
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from bleak import BleakClient
from bleak.backends.device import BLEDevice

from homeassistant.core import HomeAssistant
from ..utils import gen_entity_id
from ..const import (
    SERVICE_AUTH,
    SERVICE_BIZ,
    UUID_AUTH_INIT,
    UUID_AUTH,
    UUID_WARM_SETTING_1,
    UUID_WARM_SETTING_2,
    UUID_WARM_STATUS,
    UUID_READ_MODE_CONFIG,
    UUID_WRITE_MODE_CONFIG,
    OP_AUTH_INIT_1,
    OP_AUTH_INIT_2,
    OP_PREPARE_RAND,
    OP_PREPARE_TOKEN,
    OP_SUCCESS,
    OP_ALREADY_LOGIN,
    OP_DEV_PREPARE_RAND,
    OP_DEV_PREPARE_TOKEN,
    ACK_READY,
    ACK_SUCCESS,
    MI_ACTION_MAP,
    MI_BOOL_MAP,
    CUSTOME_MODE_ACTION_MAP,
    AVAIL_EVENT_KEY_ENTRY_ID,
    AVAIL_EVENT_KEY_AVAIL,
    AVAIL_EVENT,
    AVAIL_EVENT_KEY_IS_LOGIN,
    AVAIL_EVENT_KEY_IS_CONTROL,
    WARM_INDEX,
    HEAT_INDEX,
)

_LOGGER = logging.getLogger(__name__)


class MiKettlePro:
    """Manager for Mi Kettle Pro Bluetooth connection and data handling."""
    loop_active: bool

    def __init__(
        self,
        hass: HomeAssistant,
        ble_client: BLEDevice,
        mac_address: str,
        device_token: str,
        entry_id: str,
        poll_interval: int = 30,
        bt_interface: str | None = None,
    ) -> None:
        """Initialize the Bluetooth manager."""
        self.hass = hass
        self.mac_address = mac_address
        self.device_token = device_token
        self.poll_interval = poll_interval
        self.entry_id = entry_id
        self.entry = self.hass.config_entries.async_get_entry(self.entry_id)
        self.heat_temp_entity_id = gen_entity_id(self.entry, "number", "heat_temperature")
        self.warm_temp_entity_id = gen_entity_id(self.entry, "number", "warm_temperature")
        self.bt_interface = bt_interface

        # connection state
        self.ble_client = ble_client
        self.device: BleakClient | None = None
        self._connecting = False

        # device authentication state
        self.is_login = False
        self.app_random = None
        self.dev_random = None
        self.app_token = None
        self.dev_token = None
        self.session_key = None
        self.hmac_key = None
        self.psk = bytes.fromhex(device_token)

        # delegate
        self.received_data = {}

        # Notification waiting event dictionary, {uuid: asyncio.Event}
        self.notification_events = {}

        # Data cache
        self.cache_data = {}
        self.status_data = {}
        self._status_callbacks: list[Callable[[dict], None]] = []

        # uuid Characteristics
        self.auth = UUID_AUTH
        self.auth_init = UUID_AUTH_INIT
        self.warm_setting_1 = UUID_WARM_SETTING_1
        self.warm_setting_2 = UUID_WARM_SETTING_2
        self.warm_status = UUID_WARM_STATUS
        self.read_mode_config = UUID_READ_MODE_CONFIG
        self.write_mode_config = UUID_WRITE_MODE_CONFIG

        # Find Xiaomi private services
        self.svc_auth = None
        self.svc_biz_data = None

        # uuid required
        self._required_ble_uuids = [
            UUID_AUTH_INIT, UUID_AUTH, UUID_WARM_SETTING_1, UUID_WARM_SETTING_2,
            UUID_WARM_STATUS, UUID_READ_MODE_CONFIG, UUID_WRITE_MODE_CONFIG
        ]        

        # Error handling
        self._backoff_time = 1

        _LOGGER.debug(
            "Initialized MiKettleBluetoothManager for device %s with interface: %s",
            mac_address, self.bt_interface
        )


    def sleep(self, timeout):
        return asyncio.sleep(timeout)

    async def async_initialize(self):
        self.device = BleakClient(self.ble_client,
                                  disconnected_callback=self._async_disconnect,
                                  timeout=self.poll_interval,
                                  adapter=self.bt_interface,
                                )

        await self.setup_services()
        return True

    async def setup_services(self):
        # First connect to the device
        if not self.device.is_connected:
            await self.device.connect()

        try:
            await self.check_uuid_exist()
        except ValueError as exc:
            _LOGGER.error("Failed to check UUID existence: %s", exc)
            raise

        subscribe_uuid_list = [UUID_AUTH, UUID_AUTH_INIT, UUID_WARM_STATUS]
        await self.setup_notifications(subscribe_uuid_list)
        return

    async def setup_notifications(self, uuid_list):
        for uuid in uuid_list:
            _LOGGER.debug("\nEnabling notifications UUID %s", uuid)
            await self.device.start_notify(uuid, self.handle_notification)

    async def check_uuid_exist(self):
        _LOGGER.debug("\nDiscovering services")
        services = self.device.services

        # Print all discovered services
        _LOGGER.debug("\nAll available services:")
        for svc in services:
            _LOGGER.debug("- %s", svc.uuid)

        for svc in services:
            if str(svc.uuid).lower() == SERVICE_AUTH:
                _LOGGER.debug("\nFound Xiaomi auth service: %s", svc.uuid)
                self.svc_auth = svc

            if str(svc.uuid).lower() == SERVICE_BIZ:
                _LOGGER.debug("\nFound Xiaomi kettle service: %s", svc.uuid)
                self.svc_biz_data = svc

        if not self.svc_auth or not self.svc_biz_data:
            raise ValueError("No Service found in Device")

        auth = self.svc_auth.characteristics
        data = self.svc_biz_data.characteristics

        if not auth or not data:
            raise ValueError("No characteristics found in services")

        uuid_list = []
        for char in auth + data:
            _LOGGER.debug("- %s: Handle=0x%04x", char.uuid, char.handle)
            uuid_list.append(char.uuid.lower())

        for uuid in self._required_ble_uuids:
            if uuid not in uuid_list:
                _LOGGER.error("\nRequired Services [%s] not found", uuid)
                raise ValueError("Required MiKettlePRO Services not found")
        return

    def register_status_callback(self, callback: Callable[[dict], None]) -> None:
        """Register a callback for status updates."""
        self._status_callbacks.append(callback)

    def unregister_status_callback(self, callback: Callable[[dict], None]) -> None:
        """Unregister a status callback."""
        if callback in self._status_callbacks:
            self._status_callbacks.remove(callback)

    async def async_update_loop(self) -> None:
        """Public interface for the update loop."""
        return await self._async_update_loop()

    async def _async_update_loop(self) -> None:
        """Main update loop for Bluetooth connection and data retrieval."""
        self.update_entities_availability(False)
        try:
            while self.loop_active:
                try:
                    # Normal business logic...
                    if not self.device or not self.device.is_connected:
                        await self._async_connect()

                    if self.is_login:
                        await self._async_read_status()
                        await self.heat_safe_check()

                    # Use async sleep instead of time.sleep
                    await asyncio.sleep(self.poll_interval)

                except asyncio.CancelledError as exc:
                    _LOGGER.info("Cancel device loop task. %s", exc)

                    # Task cancelled, re-raise to terminate properly
                    raise
                except (ValueError, ConnectionError) as exc:
                    _LOGGER.error("Error in update loop: %s", exc)
                    await asyncio.sleep(min(self._backoff_time, 60))
                    self._backoff_time *= 2

        except asyncio.CancelledError:
            # Task cancelled, perform cleanup
            _LOGGER.debug("Update loop task cancelled")
            raise
        finally:
            # Ensure resource cleanup
            self._async_disconnect()

    async def _async_connect(self) -> None:
        """Connect to the Mi Kettle Pro device using configured Bluetooth interfaces."""
        if self._connecting:
            return

        self._connecting = True
        try:
            ret = await self.async_initialize()
            if not ret:
                _LOGGER.error("Failed to connect to device: async_initialize failed, device %s, interface [%s]",
                         self.mac_address, self.bt_interface)
                return
            # Perform authentication
            await self._async_device_login()
            self._connection_attempts = 0
            self._backoff_time = 1
            _LOGGER.info("Successfully connected to device %s using interface %s",
                        self.mac_address, self.bt_interface)

        except Exception as exc:
            _LOGGER.error("Failed to connect to device %s using interface %s: %s",
                         self.mac_address, self.bt_interface, exc)
            self._async_disconnect()
        finally:
            self._connecting = False

    async def _async_device_login(self) -> None:
        """Perform device authentication."""
        try:
            _LOGGER.debug("Starting device authentication")

            # Initialize authentication sequence
            await self._async_init_auth_sequence()

            is_login = await self._async_check_login_status()
            if not is_login:
                # Exchange random numbers
                await self._async_exchange_random_numbers()

                # Exchange tokens
                await self._async_exchange_tokens()

            # update_kettle_profile
            await self._async_update_kettle_mode()

            # Update entity availability after successful login
            self.update_entities_availability(True)

        except Exception as exc:
            _LOGGER.error("Device authentication failed: %s", exc)
            raise exc

    async def _async_init_auth_sequence(self) -> None:
        """Initialize authentication sequence."""
        _LOGGER.debug(
            "device auth step 01, uuid:%s, data:%s",
            self.auth_init, OP_AUTH_INIT_1.hex()
        )
        await self.write(self.auth_init, OP_AUTH_INIT_1)
        await self.sleep(0.05)
        _LOGGER.debug(
            "device auth step 02, uuid:%s, data:%s",
            self.auth_init, OP_AUTH_INIT_2.hex()
        )
        await self.write(self.auth_init, OP_AUTH_INIT_2)
        await self.sleep(0.05)

    async def _async_check_login_status(self) -> None:
        """Initialize authentication sequence."""
        login = False
        expect_value = OP_ALREADY_LOGIN
        _LOGGER.debug(
            "device auth step 03 check_login_status, uuid:%s, expect:%s",
            self.auth_init, OP_ALREADY_LOGIN.hex()
        )
        data = await self.get_notification_data(self.auth_init)
        if expect_value in data:
            login = True
            await self._handle_login_success()
        return login

    async def _async_exchange_random_numbers(self) -> None:
        _LOGGER.debug(
            "device auth step 04, uuid:%s, data:%s, expect_value:%s",
            self.auth, OP_PREPARE_RAND.hex(), ACK_READY.hex()
        )
        await self.write(self.auth, OP_PREPARE_RAND, expect_value=ACK_READY, wait_single_result=False)
        _LOGGER.debug(
            "device auth step 05 _send_app_random, uuid:%s, expect_value:%s",
            self.auth, ACK_SUCCESS.hex()
        )
        await self.write(self.auth, self._generate_rand_data(), expect_value=ACK_SUCCESS)
        _LOGGER.debug("device auth step 06 wait for DEV_PREPARE_RAND, uuid:%s", self.auth)
        await self.handle_response(self.auth, OP_DEV_PREPARE_RAND, self._handle_dev_random)  # Handle device random number

    async def _async_exchange_tokens(self) -> None:
        _LOGGER.debug("device auth step 07 wait for OP_DEV_PREPARE_TOKEN, uuid:%s", self.auth)
        await self.handle_response(self.auth, OP_DEV_PREPARE_TOKEN, self._handle_dev_token)
        _LOGGER.debug(
            "device auth step 08 send OP_PREPARE_TOKEN, uuid:%s, expect_value:%s",
            self.auth, ACK_READY.hex()
        )
        await self.write(self.auth, OP_PREPARE_TOKEN, ACK_READY)
        await self.sleep(0.05)
        _LOGGER.debug("device auth step 09 send_app_token")
        await self._send_app_token()
        _LOGGER.debug(
            "device auth step 10 wait for OP_SUCCESS, uuid:%s, expect_value:%s",
            self.auth, OP_SUCCESS.hex()
        )
        await self.handle_response(self.auth_init, OP_SUCCESS, self._handle_login_success)

    async def handle_response(self, uuid, expect_value, process_func):
        data = await self.get_notification_data(uuid)
        if expect_value in data:
            await process_func()
        else:
            raise ValueError("handle_result_response error")

    def _generate_rand_data(self):
        """Send application random number"""
        self.app_random = os.urandom(16)
        rand_data = b"\x01\x00" + self.app_random
        return rand_data

    def _get_key_from_notify_data(self, data: list):
        key : bytes = b""
        for item in data:
            if item.startswith(bytes.fromhex("0100")) or item.startswith(bytes.fromhex("0200")):
                key = key + item[2:]
                continue
        return key

    async def _handle_dev_token(self):
        await self.write(self.auth, ACK_READY)
        # wait two bluetooth frame
        data = await self.get_notification_data(self.auth, 0.5)
        key = self._get_key_from_notify_data(data)
        ret = self.verify_device_confirmation(key)
        if ret:
            await self.write(self.auth, ACK_SUCCESS)
            return
        return False

    async def _handle_login_success(self):
        self.is_login = True
        _LOGGER.info("device:[%s], login success", self.device.address)

    async def _send_app_token(self):
        """Send application token"""
        # Generate application token
        self.app_token = self._generate_app_token()

        # Send token in fragments
        token_part1 = bytes.fromhex("0100") + self.app_token[:18]
        token_part2 = bytes.fromhex("0200") + self.app_token[18:32]

        # Send first part
        await self.write(self.auth, token_part1)
        # Send second part
        await self.write(self.auth, token_part2, ACK_SUCCESS, wait_single_result=False)
        return

    async def _handle_dev_random(self):
        await self.write(self.auth, ACK_READY)
        data = await self.get_notification_data(self.auth)
        key = self._get_key_from_notify_data(data)
        self.dev_random = key  # Extract 16-byte random number
        if not key:
            msg = "Failed to get device random number"
            _LOGGER.error(msg)
            raise ValueError(msg)
        await self.write(self.auth, ACK_SUCCESS)

        # Derive session key
        return self._derive_session_key(self.app_random, self.dev_random)

    def _derive_session_key(self, app_rand, dev_rand):
        if not app_rand:
            _LOGGER.debug("app_random is not null")
            return False
        if not dev_rand:
            _LOGGER.debug("dev_random is not null")
            return False
        info_str = b"mible-login-info"
        combined = app_rand + dev_rand
        # HKDF steps
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=64,
            salt=combined,
            info=info_str
        )
        key = hkdf.derive(self.psk)

        self.session_key = key[:16]
        self.hmac_key = key[16:32]
        self.app_token = hmac.new(self.hmac_key, combined, hashlib.sha256).digest()
        return key

    def verify_device_confirmation(self, device_sig):
        """
        Verify device signature

        Args:
            device_sig: Device returned signature (bytes)

        Returns:
            bool: Verification result
        """

        # Combine random numbers (device + client)
        randoms_combo = self.dev_random + self.app_random

        # Calculate expected signature
        expected_sig = hmac.new(
            self.session_key,
            randoms_combo,
            hashlib.sha256
        ).digest()

        # Secure comparison (constant time)
        return hmac.compare_digest(device_sig, expected_sig)

    def _generate_app_token(self):
        """_generate app token"""
        input_data = self.app_random + self.dev_random
        return hmac.new(self.hmac_key, input_data, hashlib.sha256).digest()

    async def _async_read_status(self) -> None:
        """Read status data from device."""
        try:
            # This would read from UUID_WARM_STATUS characteristic
            # and parse the data using _parse_status_data
            data = self.cache_data
            status_data = self._parse_status_data(data)
            if status_data:
                self._notify_status_callbacks(status_data)
                self.status_data = status_data
            # keep connections
            await self.wait_for_notification(self.warm_status, 5)

        except Exception as exc:
            _LOGGER.error("Error reading status data: %s", exc)
            self._async_disconnect()

    async def _async_read_characteristic(self, uuid: str, expected_length: int = None) -> bytes | None:
        """Read data from a characteristic."""
        if not self.is_login:
            return

        data = await self.device.read_gatt_char(uuid)
        data_length = len(data)

        validation_failed = False
        error_msg = ""
        if expected_length and len(data) != expected_length:
            validation_failed = True
            error_msg = f"Expected length {expected_length} bytes, actual {data_length} bytes"

        if validation_failed:
            _LOGGER.error(
                "Characteristic %s data length validation failed: %s, data: %s",
                uuid, error_msg, data.hex()
            )
            return

        _LOGGER.debug("Characteristic %s read successfully: %s (length: %d bytes)", uuid, data.hex(), data_length)
        return data

    async def get_notification_data(self, uuid, timeout=0, single_result=False):
        query_num = 3
        while query_num > 0:
            if self.received_data.setdefault(uuid, []):
                break
            await self.wait_for_notification(uuid, 0.5)
            query_num -= 1
        if timeout > 0:
            await self.sleep(timeout)
            await self.wait_for_notification(uuid, 0.5)

        data = []
        while self.received_data.setdefault(uuid, []):
            item = self.received_data[uuid].pop(0)
            data.append(item)
            if single_result and len(data) == 1:
                break
        return data

    def _parse_status_data(self, data: bytes) -> dict:
        """Parse status data from device."""
        if len(data) < 11:
            _LOGGER.warning("Invalid status data length: %d", len(data))
            return

        action = MI_ACTION_MAP.get(int(data[0]), "unknown")
        is_control = True if action != "idle" and self.is_login is True else False

        return {
            "action": action,
            "is_control": is_control,
            "mode": int(data[4]),
            "mode_desc": CUSTOME_MODE_ACTION_MAP.get(int(data[4]), "unknown"),
            "current_temperature": int(data[5]),
            "warm_after_boil_raw": int(data[6]),
            "warm_after_boil": MI_BOOL_MAP.get(int(data[6]), "unknown"),
            "warm_after_take_off": MI_BOOL_MAP.get(int(data[10]), "unknown"),
            "keep_warm_time": self._bytes_to_int(data[7:9]),
        }

    def _bytes_to_int(self, bytes_data: bytes) -> int:
        """Convert bytes to integer."""
        result = 0
        for b in bytes_data:
            result = result * 256 + int(b)
        return result

    async def wait_for_notification(self, uuid, timeout=5):
        """
        Actively wait for notification with specific UUID
        :param uuid: Characteristic UUID to wait for
        :param timeout: Timeout in seconds
        :return: True=notification received, False=timeout
        """
        _LOGGER.debug("Start waiting for notification: %s, timeout=%ss", uuid, timeout)
        # Create or get event object
        if uuid not in self.notification_events or not self.notification_events[uuid]:
            self.notification_events[uuid] = asyncio.Event()

        try:
            # Asynchronously wait for event trigger
            await asyncio.wait_for(self.notification_events[uuid].wait(), timeout)
            # _LOGGER.debug("Successfully received notification: %s", uuid)
            return True
        except asyncio.TimeoutError:
            _LOGGER.warning("Waiting for notification timeout: %s", uuid)
            return False

    def handle_notification(self, sender, data):
        uuid = sender.uuid
        _LOGGER.debug(
            "[Notification] uuid: %s, Data: %s",
            uuid, binascii.hexlify(data).decode("utf-8")
        )
        if uuid in (self.auth, self.auth_init):
            self.received_data.setdefault(uuid, []).append(data)
            # _LOGGER.debug(
            #     "[Notification] uuid: %s, Data: %s, Receive: %s",
            #     uuid, binascii.hexlify(data).decode("utf-8"), self.received_data
            # )

        if uuid == self.warm_status:
            self.cache_data = data

        # Trigger waiting event (if exists)
        if uuid in self.notification_events and self.notification_events[uuid]:
            # _LOGGER.debug("Trigger notification waiting event: %s", uuid)
            self.notification_events[uuid].set()
            # Clear event reference after single trigger
            self.notification_events[uuid] = None

    async def write(self, uuid, data, expect_value=None, wait_single_result=True):
        await self.device.write_gatt_char(uuid, data, response=False)
        await self.sleep(0.05)
        _LOGGER.debug("write uuid: %s, data:%s", uuid, data.hex())
        if expect_value is not None:
            ret = bytes()
            ret = await self.get_notification_data(uuid, 1, single_result=wait_single_result)
            if expect_value not in ret:
                msg = f"Error Resp, Handle: {uuid}, Data: [{ret}], Need: [{binascii.hexlify(expect_value).decode("utf-8")}]"
                _LOGGER.error(msg)
                raise ValueError(msg)
            else:
                _LOGGER.debug(
                    "Resp OK, Handle: %s, Data: [%s], Need: [%s]",
                    uuid, ret, binascii.hexlify(expect_value).decode("utf-8")
                )
        return True

    def _notify_status_callbacks(self, data: dict) -> None:
        """Notify all registered status callbacks."""
        for callback in self._status_callbacks:
            try:
                callback(data)
            except Exception as exc:
                _LOGGER.error("Error in status callback: %s", exc)

    async def async_disconnect(self) -> None:
        """Public interface for disconnecting from device."""
        return self._async_disconnect()

    def _async_disconnect(self, client: BleakClient | None = None) -> None:
        """Disconnect from device."""
        self.is_login = False
        if not client:
            client = self.device
        if client.is_connected:
            self.hass.async_create_task(client.disconnect())
        self.received_data = {}
        self.notification_events = {}
        _LOGGER.debug("Disconnected from device")
        # Update entity availability after disconnection
        self.update_entities_availability(False)

    async def _async_update_kettle_mode(self):
        """Update kettle configuration, get temperature settings"""
        def _get_temp_by_entity_id(entity_id):
            temp_state = self.hass.states.get(entity_id)
            temperature = None
            # Parse temperature
            if temp_state and temp_state.state not in ("unknown", "unavailable"):
                try:
                    temperature = int(temp_state.state)
                    _LOGGER.debug(
                        "Got temperature setting: temperature: %s, entity_id: %s",
                        temperature, entity_id
                    )
                except ValueError:
                    _LOGGER.warning(
                        "Invalid temperature value: %s, entity_id: %s",
                        temp_state.state, entity_id
                    )
                    raise
            return temperature

        try:
            # Get heating temperature
            heat_temperature = _get_temp_by_entity_id(self.heat_temp_entity_id)

            # Get warming temperature
            warm_temperature = _get_temp_by_entity_id(self.warm_temp_entity_id)
            _LOGGER.debug(
                "get temperature from entity, heat: %s, warm: %s",
                heat_temperature, warm_temperature
            )

            data = await self._async_read_characteristic(self.read_mode_config)
            if not data:
                return

            mode_data = self.replace_mode_segment(data, WARM_INDEX, int(warm_temperature).to_bytes() + bytes.fromhex("18"))
            if not mode_data:
                return
            mode_data = self.replace_mode_segment(mode_data, HEAT_INDEX, int(heat_temperature).to_bytes()  + bytes.fromhex("18"))
            if not mode_data:
                return
            await self.write(self.write_mode_config, mode_data)
            _LOGGER.debug(
                "_async_update_kettle_mode success , write uid: %s, data: %s",
                self.write_mode_config, mode_data.hex()
            )

        except Exception as exc:
            _LOGGER.error("Failed to get temperature settings: %s", exc)
            return None

    def replace_mode_segment(self, current_data, mode_index, new_mode_data):
        """Replace specified segment data in device mode configuration

        Args:
            current_data: 10-byte original data (5 segments, 2 bytes each)
            mode_index: Segment index to modify (0-4)
            new_mode_data: New segment data (2 bytes)

        Returns:
            bytes: Modified 10-byte data
        """
        # Validate data length
        if len(current_data) != 10:
            _LOGGER.error("Invalid current_data length: expected 10 bytes, got %d", len(current_data))
            raise

        if len(new_mode_data) != 2:
            _LOGGER.error("Invalid new_mode_data length: expected 2 bytes, got %d", len(new_mode_data))
            raise

        # Split data into 5 segments, 2 bytes each
        segments = [
            current_data[0:2],  # Segment 0
            current_data[2:4],  # Segment 1
            current_data[4:6],  # Segment 2
            current_data[6:8],  # Segment 3
            current_data[8:10]  # Segment 4
        ]

        # Replace specified segment data
        segments[mode_index] = new_mode_data

        # Recombine all segments
        modified_data = b"".join(segments)

        _LOGGER.debug("Mode data subsituted: index=%d, new_data=%s, result=%s",
                    mode_index, new_mode_data.hex(), modified_data.hex())

        return modified_data

    def read_mode_segment(self, current_data, mode_index):
        """Search for specified segment data in device mode configuration

        Args:
            current_data: 10-byte original data (5 segments, 2 bytes each)
            mode_index: Segment index to modify (0-4)

        Returns:
            bytes: Modified 2-byte data
        """
        # Validate data length
        if len(current_data) != 10:
            _LOGGER.error("Invalid current_data length: expected 10 bytes, got %d", len(current_data))
            raise

        # Split data into 5 segments, 2 bytes each
        segments = [
            current_data[0:2],  # Segment 0
            current_data[2:4],  # Segment 1
            current_data[4:6],  # Segment 2
            current_data[6:8],  # Segment 3
            current_data[8:10]  # Segment 4
        ]

        ret = segments[mode_index]

        if len(ret) != 2:
            _LOGGER.error("Invalid mode_index_data length: expected 2 bytes, got %d", len(ret))
            raise

        return ret

    async def modify_mode_config_by_index(self, index_desc, temperature):
        """
        used by number entity, heat and warm
        """
        data = await self._async_read_characteristic(self.read_mode_config)
        if not data:
            return

        mode_index = 0
        if index_desc == "heat_temperature":
            mode_index = HEAT_INDEX
        elif index_desc == "warm_temperature":
            mode_index = WARM_INDEX
        else:
            _LOGGER.error(
                "modify_mode_config_by_segment failed, unsupport index_desc: %s",
                index_desc
            )
        mode_data = self.replace_mode_segment(data, mode_index, int(temperature).to_bytes() + bytes.fromhex("18"))
        if not mode_data:
            return

        await self.write(self.write_mode_config, mode_data)
        _LOGGER.debug(
            "_async_update_kettle_mode success , write uid: %s, data: %s",
            self.write_mode_config, mode_data.hex()
        )

    async def async_read_mode_config_by_index(self, mode_index):
        data = await self._async_read_characteristic(self.read_mode_config)
        if not data:
            return

        mode_data = self.read_mode_segment(data, mode_index)
        if not mode_data:
            return

        return {
            "temperature": int(mode_data[0]),
            "keep_warm_duration": int(mode_data[1])
        }

    def update_entities_availability(self, available: bool) -> None:
        """Notify all entities to update availability via event"""
        if not self.entry_id:
            _LOGGER.warning("Cannot update entity availability: Device Entry ID not set")
            return

        event_data = {
            AVAIL_EVENT_KEY_ENTRY_ID: self.entry_id,
            AVAIL_EVENT_KEY_AVAIL: available,
            AVAIL_EVENT_KEY_IS_LOGIN: self.is_login,
        }
        self.hass.bus.async_fire(AVAIL_EVENT, event_data)
        _LOGGER.debug("Published availability event: Device %s event_data=%r status_data=%r", 
                      self.entry_id, event_data, self.status_data)

    async def action_async(self, action):
        warm_after_boil_bytes = self.status_data["warm_after_boil_raw"].to_bytes()
        if action == "heat":
            await self.write(self.warm_setting_1, bytes.fromhex("04") + warm_after_boil_bytes)
            _LOGGER.debug("start heat water")
        elif action in ["turn_off_heat", "warm"]:
            await self.write(self.warm_setting_1, bytes.fromhex("03") + warm_after_boil_bytes)
        elif action == "turn_off_keep_warm":
            mode = self.get_current_mode()
            if mode >= 0 and mode <= 4:
                await self.write(self.warm_setting_1, int(mode).to_bytes() + bytes.fromhex("00"))
            else:
                _LOGGER.error("Failed to turn off_keep_warm, mode[%s] not range from 0 to 4", mode)

    def get_current_mode(self):
        """get current warm mode"""
        status_data = self._parse_status_data(self.cache_data)
        if not status_data:
            return
        mode = status_data.get("mode", None)
        if not mode >= 0:
            _LOGGER.error("Get_current_mode failed, mode: %s", mode)
        return mode

    async def _monitor_for_temperature(self, target_temp, callback: Callable):
        """Monitor until target temperature is reached"""
        status = self._parse_status_data(self.cache_data)
        if status and status.get("current_temperature") >= target_temp:
            _LOGGER.debug("current temperature: %s", status.get("current_temperature"))
            await callback()
            _LOGGER.debug("turn off heat success")

    async def heat_safe_check(self):
        mode = self.get_current_mode()
        if not mode  >= 0:
            _LOGGER.error("turn off heating failed, mode: %s", mode)
            return
        if mode == HEAT_INDEX:
            ret = await self.async_read_mode_config_by_index(mode)
            if not ret:
                _LOGGER.error("turn off heating failed, ret: %s", ret)
                return
            target_temp = ret["temperature"]
            _LOGGER.debug("check if mode temperature reached, mode: %s, target_temp: %s", mode, target_temp)
            await self._monitor_for_temperature(target_temp, lambda: self.action_async("turn_off_heat"))
