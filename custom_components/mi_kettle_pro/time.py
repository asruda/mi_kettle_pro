"""Time platform for Mi Kettle Pro integration."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .device_config import DEVICE_CONFIGS
from .utils import gen_entity_id


PLATFORM = "time"

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Mi Kettle Pro time entities from a config entry."""

    entities = []
    device_model = hass.data[DOMAIN][f"{entry.entry_id}_device_model"]
    config = DEVICE_CONFIGS.get(device_model, {})["entities"].get(PLATFORM, [])
    if config:
        for item in config:
            entities.append(globals()[item](entry))

    async_add_entities(entities, update_before_add=True)


class MiKettleProScheduledBoilTime(TimeEntity):
    """Representation of a Mi Kettle Pro scheduled boil time entity."""

    _attr_has_entity_name = True
    _attr_name = "Scheduled Boil"
    _attr_unique_id = "scheduled_boil"
    _attr_icon = "mdi:clock-outline"

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the scheduled boil time entity."""
        self._entry = entry
        self.entity_id = gen_entity_id(entry, PLATFORM, self._attr_unique_id)
        self._attr_unique_id = self.entity_id
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.data.get("device_name", "Mi Kettle Pro"),
            "manufacturer": "Xiaomi",
            "model": "Mi Kettle Pro",
        }
        self._scheduled_time = None

    @property
    def native_value(self) -> time | None:
        """Return the current scheduled time value."""
        return self._scheduled_time

    async def async_set_value(self, value: time) -> None:
        """Set the scheduled time value."""
        # TODO: Implement actual device scheduling
        self._scheduled_time = value
        self.async_write_ha_state()
