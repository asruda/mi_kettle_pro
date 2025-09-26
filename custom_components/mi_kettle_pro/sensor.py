"""Sensor platform for Mi Kettle Pro integration."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from .const import (
    DOMAIN,
    AVAIL_EVENT_KEY_ENTRY_ID,
    AVAIL_EVENT_KEY_AVAIL,
    AVAIL_EVENT,
    CONF_TEMPERATURE_UNIT,
)
from .device_config import DEVICE_CONFIGS
from .utils import gen_entity_id


PLATFORM = "sensor"

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Mi Kettle Pro sensors from a config entry."""

    sensors = []
    device_model = hass.data[DOMAIN][f"{entry.entry_id}_device_model"]
    config = DEVICE_CONFIGS.get(device_model, [])
    if config:
        for sensor in config["entities"][PLATFORM]:
            sensors.append(globals()[sensor](entry))

    async_add_entities(sensors, update_before_add=True)

class MiKettleSensor(SensorEntity):
    """Base sensor entity for MiKettle devices."""

    _attr_unique_name = "no set"
    _status_key = "no set"

    def __init__(self, entry):
        """Initialize the sensor."""
        self._entry = entry
        self.entity_id = gen_entity_id(entry, PLATFORM, self._attr_unique_name)
        self._attr_unique_id = self.entity_id
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.data.get("device_name", "Mi Kettle Pro"),
            "manufacturer": "Xiaomi",
            "model": "Mi Kettle Pro",
        }
        self._device_manager = None
        self._listener = None

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        device_manager_key = f"{self._entry.entry_id}_device_manager"
        self._device_manager = self.hass.data[DOMAIN].get(device_manager_key)

        if self._device_manager:
            self._device_manager.device_parser.register_status_callback(
                self._handle_status_update
            )

        # Register availability event listener
        self._listener = self.hass.bus.async_listen(
            AVAIL_EVENT,
            self._handle_availability_changed
        )

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        if self._device_manager:
            self._device_manager.device_parser.unregister_status_callback(
                self._handle_status_update
            )

        # Remove availability event listener
        if self._listener:
            self._listener()

    def _handle_availability_changed(self, event) -> None:
        """Handle availability change events."""
        if event.data.get(AVAIL_EVENT_KEY_ENTRY_ID) == self._entry.entry_id:
            self._attr_available = event.data.get(AVAIL_EVENT_KEY_AVAIL, False)
            self.hass.loop.call_soon_threadsafe(self.async_write_ha_state)

    def _handle_status_update(self, status_data: dict) -> None:
        """Handle status updates from Device manager."""
        if status_data:
            self._attr_native_value = status_data.get(
                self._status_key, "unknown"
            )
            self.hass.loop.call_soon_threadsafe(self.async_write_ha_state)

class MiKettleProStatusSensor(MiKettleSensor):
    """Representation of a Mi Kettle Pro status sensor."""

    _attr_has_entity_name = True
    _attr_name = "Device Status"
    _attr_unique_name = "status"
    _status_key = "action"

    @property
    def native_value(self) -> StateType:
        """Return the translated status value."""
        original_value = self._attr_native_value
        if original_value is None:
            return None

        # Use translation keys, Home Assistant will handle translation automatically
        # Translation key format: entity.sensor.state.{status_value}
        return original_value


class MiKettleProCurrentTemperatureSensor(MiKettleSensor):
    """Representation of a Mi Kettle Pro current temperature sensor."""

    _attr_has_entity_name = True
    _attr_name = "Current Temperature"
    _attr_device_class = "temperature"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_unique_name = "current_temperature"
    _status_key = "current_temperature"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the controllable sensor."""
        self._entry = entry
        self.suggested_unit_of_measurement = self._entry.data.get(
            CONF_TEMPERATURE_UNIT, UnitOfTemperature.CELSIUS
        )
        super().__init__(entry)

    def _handle_status_update(self, status_data: dict) -> None:
        """Handle status updates from device manager."""
        if status_data:
            self._attr_native_unit_of_measurement = (
                self.suggested_unit_of_measurement
            )
            temperature_celsius = status_data.get(self._status_key)
            if temperature_celsius is not None:
                self._attr_native_value = temperature_celsius
                self.hass.loop.call_soon_threadsafe(self.async_write_ha_state)

    @property
    def native_value(self) -> StateType:
        """Return the native value of the sensor."""
        return self._attr_native_value

class MiKettleProOperationModeSensor(MiKettleSensor):
    """Representation of a Mi Kettle Pro controllable sensor."""

    _attr_has_entity_name = True
    _attr_name = "Operational Mode"
    _attr_unique_id = "operational_mode"
    _status_key = "action"
    _attr_icon = "mdi:remote"

    @property
    def native_value(self) -> StateType:
        """Return the current status value."""
        return "control" if self._attr_native_value else "monitor"

    def _handle_status_update(self, status_data: dict) -> None:
        """Handle status updates from Bluetooth manager."""
        if status_data:
            action = status_data.get(self._status_key, "unknown")
            self._attr_native_value = True if action != "idle" else False
            self.hass.loop.call_soon_threadsafe(self.async_write_ha_state)
