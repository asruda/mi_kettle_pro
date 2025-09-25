"""MiKettle Pro specific device implementation."""

import asyncio
import binascii
import logging
import hashlib
import hmac
import os
from types import coroutine
from typing import Callable
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
    # uuid required
    CHECK_UUID_LIST = [
        UUID_AUTH_INIT, UUID_AUTH, UUID_WARM_SETTING_1, UUID_WARM_SETTING_2,
        UUID_WARM_STATUS, UUID_READ_MODE_CONFIG, UUID_WRITE_MODE_CONFIG
    ]
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

        # 新增：通知等待事件字典 {uuid: asyncio.Event}
        self.notification_events = {}

        # Data cache
        self.cache_data = {}
        self.status_data = {}
        self._status_callbacks: list[Callable[[dict], None]] = []

        # Error handling
        self._connection_attempts = 0
        self._last_connection_attempt = None
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
        # 先连接设备
        if not self.device.is_connected:
            await self.device.connect()

        try:
            await self.check_uuid_exist()
        except ValueError as exc:
            _LOGGER.error("Failed to check UUID existence: %s", exc)
            raise

        self.auth = UUID_AUTH
        self.auth_init = UUID_AUTH_INIT
        self.warm_setting_1 = UUID_WARM_SETTING_1
        self.warm_setting_2 = UUID_WARM_SETTING_2
        self.warm_status = UUID_WARM_STATUS
        self.read_mode_config = UUID_READ_MODE_CONFIG
        self.write_mode_config = UUID_WRITE_MODE_CONFIG
        subscribe_uuid_list = [UUID_AUTH, UUID_AUTH_INIT, UUID_WARM_STATUS]
        await self.setup_notifications(subscribe_uuid_list)
        return

    async def setup_notifications(self, uuid_list):
        for uuid in uuid_list:
            _LOGGER.debug("\nEnabling notifications UUID %s...", uuid)
            await self.device.start_notify(uuid, self.handle_notification)

    async def check_uuid_exist(self):
        _LOGGER.debug("\nDiscovering services...")
        services = self.device.services

        # 打印所有发现的服务
        _LOGGER.debug("\nAll available services:")
        for svc in services:
            _LOGGER.debug("- %s", svc.uuid)

        # 查找小米私有服务
        self.svc_auth = None
        self.svc_biz_data = None

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

        for uuid in self.CHECK_UUID_LIST:
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
                    # 正常的业务逻辑...
                    if not self.device or not self.device.is_connected:
                        await self._async_connect()

                    if self.is_login:
                        await self._async_read_status()
                        await self.heat_safe_check()

                    # 使用异步等待而不是 time.sleep
                    await asyncio.sleep(self.poll_interval)

                except asyncio.CancelledError as exc:
                    _LOGGER.info("Cancel device loop task. %s", exc)

                    # 任务被取消，重新抛出以正确终止
                    raise
                except (ValueError, ConnectionError) as exc:
                    _LOGGER.error("Error in update loop: %s", exc)
                    await asyncio.sleep(min(self._backoff_time, 60))
                    self._backoff_time *= 2

        except asyncio.CancelledError:
            # 任务被取消，进行清理工作
            _LOGGER.debug("Update loop task cancelled")
            raise
        finally:
            # 确保资源清理
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

            # 登录成功后更新实体可用性
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
        await self.handle_response(self.auth, OP_DEV_PREPARE_RAND, self._handle_dev_random)  # 处理设备随机数

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
        """发送应用随机数"""
        self.app_random = os.urandom(16)
        rand_data = b'\x01\x00' + self.app_random
        return rand_data

    def _get_key_from_notify_data(self, data: list):
        key : bytes = b''
        for item in data:
            if item.startswith(bytes.fromhex('0100')) or item.startswith(bytes.fromhex('0200')):
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
        """发送应用令牌"""
        # 生成应用令牌
        self.app_token = self._generate_app_token()

        # 分片发送令牌
        token_part1 = bytes.fromhex("0100") + self.app_token[:18]
        token_part2 = bytes.fromhex("0200") + self.app_token[18:32]

        # 发送第一部分
        await self.write(self.auth, token_part1)
        # 发送第二部分
        await self.write(self.auth, token_part2, ACK_SUCCESS, wait_single_result=False)
        return

    async def _handle_dev_random(self):
        await self.write(self.auth, ACK_READY)
        data = await self.get_notification_data(self.auth)
        key = self._get_key_from_notify_data(data)
        self.dev_random = key  # 提取16字节随机数
        if not key:
            msg = "获取设备随机数失败"
            _LOGGER.error(msg)
            raise ValueError(msg)
        await self.write(self.auth, ACK_SUCCESS)

        # 派生会话密钥
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
        # HKDF步骤
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
        验证设备签名

        参数:
            device_sig: 设备返回的签名(字节串)

        返回:
            bool: 验证结果
        """

        # 组合随机数 (设备+客户端)
        randoms_combo = self.dev_random + self.app_random

        # 计算预期签名
        expected_sig = hmac.new(
            self.session_key,
            randoms_combo,
            hashlib.sha256
        ).digest()

        # 安全比较 (恒定时间)
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
            error_msg = f"期望长度 {expected_length} 字节, 实际 {data_length} 字节"

        if validation_failed:
            _LOGGER.error(
                "特征值 %s 数据长度验证失败: %s, 数据: %s",
                uuid, error_msg, data.hex()
            )
            return

        _LOGGER.debug("特征值 %s 读取成功: %s (长度: %d 字节)", uuid, data.hex(), data_length)
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
        is_control = False if action == "idle" else True

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
        主动等待特定UUID的通知
        :param uuid: 要等待的特征UUID
        :param timeout: 超时时间（秒）
        :return: True=收到通知, False=超时
        """
        _LOGGER.debug("开始等待通知: %s, 超时=%ss", uuid, timeout)
        # 创建或获取事件对象
        if uuid not in self.notification_events or not self.notification_events[uuid]:
            self.notification_events[uuid] = asyncio.Event()

        try:
            # 异步等待事件触发
            await asyncio.wait_for(self.notification_events[uuid].wait(), timeout)
            # _LOGGER.debug("成功收到通知: %s", uuid)
            return True
        except asyncio.TimeoutError:
            _LOGGER.warning("等待通知超时: %s", uuid)
            return False

    def handle_notification(self, sender, data):
        uuid = sender.uuid
        _LOGGER.debug(
            "[Notification] uuid: %s, Data: %s",
            uuid, binascii.hexlify(data).decode('utf-8')
        )
        if uuid in (self.auth, self.auth_init):
            self.received_data.setdefault(uuid, []).append(data)
            # _LOGGER.debug(
            #     "[Notification] uuid: %s, Data: %s, Receive: %s",
            #     uuid, binascii.hexlify(data).decode('utf-8'), self.received_data
            # )

        if uuid == self.warm_status:
            self.cache_data = data

        # 触发等待事件（如果存在）
        if uuid in self.notification_events and self.notification_events[uuid]:
            # _LOGGER.debug("触发通知等待事件: %s", uuid)
            self.notification_events[uuid].set()
            # 单次触发后清除事件引用
            self.notification_events[uuid] = None

    async def write(self, uuid, data, expect_value=None, wait_single_result=True):
        await self.device.write_gatt_char(uuid, data, response=False)
        await self.sleep(0.05)
        _LOGGER.debug("write uuid: %s, data:%s", uuid, data.hex())
        if expect_value is not None:
            ret = bytes()
            ret = await self.get_notification_data(uuid, 1, single_result=wait_single_result)
            if expect_value not in ret:
                msg = f"Error Resp, Handle: {uuid}, Data: [{ret}], Need: [{binascii.hexlify(expect_value).decode('utf-8')}]"
                _LOGGER.error(msg)
                raise ValueError(msg)
            else:
                _LOGGER.debug(
                    "Resp OK, Handle: %s, Data: [%s], Need: [%s]",
                    uuid, ret, binascii.hexlify(expect_value).decode('utf-8')
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
        # 断开连接后更新实体可用性
        self.update_entities_availability(False)

    async def _async_update_kettle_mode(self):
        def _get_temp_by_entity_id(entity_id):
            temp_state = self.hass.states.get(entity_id)
            temperature = None
            # 解析温度
            if temp_state and temp_state.state not in ("unknown", "unavailable"):
                try:
                    temperature = int(temp_state.state)
                    _LOGGER.debug(
                        "获取到温度设置: temperature: %s, entity_id: %s",
                        temperature, entity_id
                    )
                except ValueError:
                    _LOGGER.warning(
                        "无效的温度值: %s, entity_id: %s",
                        temp_state.state, entity_id
                    )
                    raise
            return temperature

        """更新水壶配置，获取温度设置值"""
        try:
            # 获取加热温度
            heat_temperature = _get_temp_by_entity_id(self.heat_temp_entity_id)

            # 获取保温温度
            warm_temperature = _get_temp_by_entity_id(self.warm_temp_entity_id)
            _LOGGER.debug(
                "get temperature entity, heat: %s, warm: %s",
                heat_temperature, warm_temperature
            )

            data = await self._async_read_characteristic(self.read_mode_config)
            if not data:
                return

            mode_data = self.replace_mode_segment(data, WARM_INDEX, int(warm_temperature).to_bytes() + bytes.fromhex('18'))
            if not mode_data:
                return
            mode_data = self.replace_mode_segment(mode_data, HEAT_INDEX, int(heat_temperature).to_bytes()  + bytes.fromhex('18'))
            if not mode_data:
                return
            await self.write(self.write_mode_config, mode_data)
            _LOGGER.debug(
                "_async_update_kettle_mode success , write uid: %s, data: %s",
                self.write_mode_config, mode_data.hex()
            )

        except Exception as exc:
            _LOGGER.error("获取温度设置失败: %s", exc)
            return None

    def replace_mode_segment(self, current_data, mode_index, new_mode_data):
        """替换设备模式配置中的指定段数据

        Args:
            current_data: 10字节的原始数据（5段，每段2字节）
            mode_index: 要修改的段索引（0-4）
            new_mode_data: 新的段数据（2字节）

        Returns:
            bytes: 修改后的10字节数据
        """
        # 验证数据长度
        if len(current_data) != 10:
            _LOGGER.error("Invalid current_data length: expected 10 bytes, got %d", len(current_data))
            raise

        if len(new_mode_data) != 2:
            _LOGGER.error("Invalid new_mode_data length: expected 2 bytes, got %d", len(new_mode_data))
            raise

        # 将数据分成5段，每段2字节
        segments = [
            current_data[0:2],  # 段0
            current_data[2:4],  # 段1
            current_data[4:6],  # 段2
            current_data[6:8],  # 段3
            current_data[8:10]  # 段4
        ]

        # 替换指定段的数据
        segments[mode_index] = new_mode_data

        # 重新组合所有段
        modified_data = b''.join(segments)

        _LOGGER.debug("Mode data subsituted: index=%d, new_data=%s, result=%s",
                    mode_index, new_mode_data.hex(), modified_data.hex())

        return modified_data

    def read_mode_segment(self, current_data, mode_index):
        """搜索设备模式配置中的指定段数据

        Args:
            current_data: 10字节的原始数据（5段，每段2字节）
            mode_index: 要修改的段索引（0-4）

        Returns:
            bytes: 修改后的2字节数据
        """
        # 验证数据长度
        if len(current_data) != 10:
            _LOGGER.error("Invalid current_data length: expected 10 bytes, got %d", len(current_data))
            raise

        # 将数据分成5段，每段2字节
        segments = [
            current_data[0:2],  # 段0
            current_data[2:4],  # 段1
            current_data[4:6],  # 段2
            current_data[6:8],  # 段3
            current_data[8:10]  # 段4
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
        mode_data = self.replace_mode_segment(data, mode_index, int(temperature).to_bytes() + bytes.fromhex('18'))
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
        """通过事件通知所有实体更新可用性"""
        if not self.entry_id:
            _LOGGER.warning("无法更新实体可用性：设备Entry ID未设置")
            return

        event_data = {
            AVAIL_EVENT_KEY_ENTRY_ID: self.entry_id,
            AVAIL_EVENT_KEY_AVAIL: available,
            AVAIL_EVENT_KEY_IS_LOGIN: self.is_login,
            AVAIL_EVENT_KEY_IS_CONTROL: self.status_data.get(AVAIL_EVENT_KEY_IS_CONTROL, False)
        }
        self.hass.bus.async_fire(AVAIL_EVENT, event_data)
        _LOGGER.debug("发布可用性事件: 设备 %s 可用性=%s", self.entry_id, available)

    async def action_async(self, action):
        warm_after_boil_bytes = self.status_data["warm_after_boil_raw"].to_bytes()
        if action == "heat":
            await self.write(self.warm_setting_1, bytes.fromhex('04') + warm_after_boil_bytes)
            _LOGGER.debug("start heat water")
        elif action in ["turn_off_heat", "warm"]:
            await self.write(self.warm_setting_1, bytes.fromhex('03') + warm_after_boil_bytes)
        elif action == "turn_off_keep_warm":
            mode = self.get_current_mode()
            if mode:
                await self.write(self.warm_setting_1, int(mode).to_bytes() + bytes.fromhex('00'))
            else:
                _LOGGER.error("turn_off_keep_warm failed")

    def get_current_mode(self):
        """get current warm mode"""
        status_data = self._parse_status_data(self.cache_data)
        if not status_data:
            return
        mode = status_data.get("mode", None)
        if not mode >= 0:
            _LOGGER.error("get_current_mode failed, mode: %s", mode)
        return mode

    async def _monitor_for_temperature(self, target_temp, callback: Callable):
        """监控直到达到目标温度"""
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
