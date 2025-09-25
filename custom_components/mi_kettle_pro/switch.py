"""Switch platform for Mi Kettle Pro integration."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .device_config import DEVICE_CONFIGS
from .utils import gen_entity_id


PLATFORM = "switch"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Mi Kettle Pro switches from a config entry."""

    entities = []
    device_model = hass.data[DOMAIN][f"{entry.entry_id}_device_model"]
    config = DEVICE_CONFIGS.get(device_model, {})["entities"].get(PLATFORM, [])
    if config:
        for item in config:
            entities.append(globals()[item](entry))

    async_add_entities(entities, update_before_add=True)


class MiKettleProAutoKeepWarmSwitch(SwitchEntity):
    """Representation of a Mi Kettle Pro auto keep-warm switch."""

    _attr_has_entity_name = True
    _attr_name = "Auto Keep-warm after Lift-off"
    _attr_unique_id = "auto_keep_warm_after_liftoff"
    _attr_icon = "mdi:kettle-steam"

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the auto keep-warm switch."""
        self._entry = entry
        self.entity_id = gen_entity_id(entry, PLATFORM, self._attr_unique_id)
        self._attr_unique_id = self.entity_id
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.data.get("device_name", "Mi Kettle Pro"),
            "manufacturer": "Xiaomi",
            "model": "Mi Kettle Pro",
        }
        self._is_on = False

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        return self._is_on

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        # TODO: Implement actual device control
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        # TODO: Implement actual device control
        self._is_on = False
        self.async_write_ha_state()
