"""Button platform for Mi Kettle Pro integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import (
    DOMAIN,
    AVAIL_EVENT_KEY_ENTRY_ID,
    AVAIL_EVENT_KEY_IS_CONTROL,
    AVAIL_EVENT,
    AVAIL_EVENT_KEY_AVAIL,
)
from .device_config import DEVICE_CONFIGS
from .utils import gen_entity_id

PLATFORM = "button"

class MiKettleProButtonException(Exception):
    def __init__(self, message="An error occurred in MiKettle Pro Button") -> None:
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return f'MiKettleProButtonException: {self.message}'

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Mi Kettle Pro buttons from a config entry."""
    buttons = []
    device_model = hass.data[DOMAIN][f"{entry.entry_id}_device_model"]
    config = DEVICE_CONFIGS.get(device_model, [])
    if config:
        for button in config["entities"]["button"]:
            buttons.append(globals()[button](entry))

    async_add_entities(buttons, update_before_add=True)


class MiKettleProBaseButton(ButtonEntity):
    """Base class for Mi Kettle Pro button entities."""
    _attr_has_entity_name = True
    _attr_unique_name = "no set"
    _device_manager = None

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the base button entity."""
        self._entry = entry
        self.entity_id = gen_entity_id(entry, PLATFORM, self._attr_unique_name)
        self._attr_unique_id = self.entity_id
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.data.get("device_name", "Mi Kettle Pro"),
            "manufacturer": "Xiaomi",
            "model": "Mi Kettle Pro",
        }
        self._listener = None

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        self._hass = self.hass
        device_manager_key = f"{self._entry.entry_id}_device_manager"
        self._device_manager = self._hass.data[DOMAIN].get(device_manager_key)

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
            self._attr_available = status_data.get(
                AVAIL_EVENT_KEY_IS_CONTROL, False
            )
            self.hass.loop.call_soon_threadsafe(self.async_write_ha_state)

    async def action_async(self) -> None:
        """Execute the button action."""
        action = self._attr_unique_name
        try:
            return await self._device_manager.device_parser.action_async(action)
        except MiKettleProButtonException as e:
            raise RuntimeError(
                f"{e}, {self.entity_id}, action: {action}"
            ) from e

    async def async_press(self) -> None:
        """Handle the button press."""
        return await self.action_async()


class MiKettleProHeatButton(MiKettleProBaseButton):
    """Representation of a Mi Kettle Pro Heat button."""
    _attr_translation_key = "heat"
    _attr_unique_name = "heat"
    _attr_icon = "mdi:kettle-steam"

class MiKettleProWarmButton(MiKettleProBaseButton):
    """Representation of a Mi Kettle Pro warm button."""

    _attr_translation_key = "warm"
    _attr_unique_name = "warm"
    _attr_icon = "mdi:kettle"


class MiKettleProTurnOffBoilButton(MiKettleProBaseButton):
    """Representation of a Mi Kettle Pro turn off boil button."""

    _attr_translation_key = "turn_off_heat"
    _attr_unique_name = "turn_off_boil"
    _attr_icon = "mdi:fire-off"


class MiKettleProTurnOffWarmButton(MiKettleProBaseButton):
    """Representation of a Mi Kettle Pro turn off keep-warm button."""

    _attr_translation_key = "turn_off_keep_warm"
    _attr_unique_name = "turn_off_warm"
    _attr_icon = "mdi:thermometer-off"
