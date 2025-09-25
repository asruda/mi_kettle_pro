"""The Mi Kettle Pro integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .device_helpers import MiKettleProManager
from .const import (
        DOMAIN,
        CONF_BT_INTERFACE,
    )
import logging

_LOGGER = logging.getLogger(__name__)

_PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.TIME,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Mi Kettle Pro from a config entry."""

    # Store the config entry data for platforms to access
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    try:
        # Initialize Device manager
        device_manager = MiKettleProManager(
            hass=hass,
            entry=entry,
        )
        interface_list = entry.data[CONF_BT_INTERFACE]
        if "disable" in interface_list:
            return False
        for interface in interface_list:
            ret = await device_manager.async_setup(interface)
            if not ret:
                _LOGGER.debug(
                    "connect to device: %s failed, bt interface:%s",
                    entry.data["mac"],
                    interface,
                )
                continue

            # Store Device manager
            hass.data[DOMAIN][f"{entry.entry_id}_device_manager"] = (
                device_manager
            )

            # Start Device manager
            await device_manager.async_start()
            await hass.config_entries.async_forward_entry_setups(
                entry, _PLATFORMS
            )
            return True
        raise Exception(
            f"unable to connect to device: {entry.data["mac"]}, bt interface list:{interface_list}"
        )

    except Exception as e:
        msg = f"Fail to async_setup_entry, except: {e}"
        raise ConfigEntryNotReady(msg) from e
    return False

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Stop Device manager
    device_manager_key = f"{entry.entry_id}_device_manager"
    if device_manager := hass.data[DOMAIN].get(device_manager_key):
        await device_manager.async_stop()
        hass.data[DOMAIN].pop(device_manager_key)

    if unload_ok := await hass.config_entries.async_unload_platforms(
        entry, _PLATFORMS
    ):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
