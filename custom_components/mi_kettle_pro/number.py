"""Number platform for Mi Kettle Pro integration."""

from __future__ import annotations

from homeassistant.components.number import (
    NumberEntity, NumberMode, NumberDeviceClass
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    CONF_BOIL_TEMPERATURE,
    CONF_WARM_TEMPERATURE,
    DEFAULT_BOIL_TEMPERATURE,
    DEFAULT_WARM_TEMPERATURE,
    MIN_BOIL_TEMPERATURE,
    MAX_BOIL_TEMPERATURE,
    MIN_WARM_TEMPERATURE,
    MAX_WARM_TEMPERATURE,
)
from .utils import gen_entity_id
from .device_config import DEVICE_CONFIGS


PLATFORM = "number"

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Mi Kettle Pro number entities from a config entry."""

    entities = []
    device_model = hass.data[DOMAIN][f"{entry.entry_id}_device_model"]
    config = DEVICE_CONFIGS.get(device_model, {})["entities"].get(PLATFORM, [])
    if config:
        for item in config:
            entities.append(globals()[item](entry))

    async_add_entities(entities, update_before_add=True)


class MiKettleProBaseNumber(NumberEntity):
    """Base class for Mi Kettle Pro number entities."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_unique_name = "no set"
    _attr_unique_id = "no set"

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the base number entity."""
        self._entry = entry
        self.entity_id = gen_entity_id(entry, PLATFORM, self._attr_unique_id)
        self._attr_unique_id = self.entity_id
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.data.get("device_name", "Mi Kettle Pro"),
            "manufacturer": "Xiaomi",
            "model": "Mi Kettle Pro",
        }

        # 防抖相关属性
        self._debounce_timer = None
        self._debounce_delay = 0.5
        self._pending_value = None

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        device_manager_key = f"{self._entry.entry_id}_device_manager"
        self._device_manager = self.hass.data[DOMAIN].get(device_manager_key)

    async def _async_debounced_set_value(self, value: float) -> None:
        """防抖后的实际设置值方法"""
        # 取消之前的定时器
        if self._debounce_timer:
            self._debounce_timer.cancel()

        # 设置新的定时器
        self._debounce_timer = self.hass.loop.call_later(
            self._debounce_delay,
            lambda: self.hass.async_create_task(self._async_apply_value(value))
        )

    async def async_set_native_value(self, value: float) -> None:
        """Set the boil temperature value with debounce."""
        await self._async_debounced_set_value(value)

    async def _async_apply_value(self, value: float) -> None:
        """实际应用值的逻辑"""
        self._attr_native_value = int(value)
        await self._device_manager.device_parser.modify_mode_config_by_index(
            self._attr_unique_name, value
        )
        self.async_write_ha_state()
        self._debounce_timer = None

class MiKettleProBoilTemperatureNumber(MiKettleProBaseNumber):
    """Representation of a Mi Kettle Pro boil temperature number entity."""

    _attr_name = "Boil Temperature"
    _attr_unique_name = "boil_temperature"
    _attr_unique_id = "boil_temperature"
    _attr_native_min_value = MIN_BOIL_TEMPERATURE
    _attr_native_max_value = MAX_BOIL_TEMPERATURE
    _attr_native_step = 1.0
    _attr_icon = "mdi:thermometer-high"

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the boil temperature number entity."""
        # 从配置中读取煮沸温度值，如果没有则使用默认值
        self._attr_native_value = float(
            entry.data.get(CONF_BOIL_TEMPERATURE, DEFAULT_BOIL_TEMPERATURE)
        )
        super().__init__(entry)


class MiKettleProWarmTemperatureNumber(MiKettleProBaseNumber):
    """Representation of a Mi Kettle Pro warm temperature number entity."""

    _attr_name = "Warm Temperature"
    _attr_unique_name = "warm_temperature"
    _attr_unique_id = "warm_temperature"
    _attr_native_min_value = MIN_WARM_TEMPERATURE
    _attr_native_max_value = MAX_WARM_TEMPERATURE
    _attr_native_step = 1.0
    _attr_icon = "mdi:water-thermometer"

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the warm temperature number entity."""
        # 从配置中读取保温温度值，如果没有则使用默认值
        self._attr_native_value = float(
            entry.data.get(CONF_WARM_TEMPERATURE, DEFAULT_WARM_TEMPERATURE)
        )
        super().__init__(entry)
