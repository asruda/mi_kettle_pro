"""Device base classes for MiKettle Pro integration."""

from abc import ABC, abstractmethod
import logging
from typing import Any, Dict, List

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity


class MiKettleDevice(ABC):
    """Base class for all MiKettle devices."""

    def __init__(
        self,
        hass: HomeAssistant,
        mac_address: str,
        device_config: dict[str, Any]
    ) -> None:
        self.hass = hass
        self.mac_address = mac_address
        self.config = device_config
        self.entities: list[Entity] = []

    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the device."""
        pass

    @abstractmethod
    async def update_data(self) -> dict[str, Any]:
        """Update device data."""
        pass

    @abstractmethod
    async def execute_command(
        self, command: str, params: dict[str, Any] = None
    ) -> bool:
        """Execute a device command."""
        pass

    def get_entities(self) -> List[Entity]:
        """Get all entities for this device."""
        return self.entities

    def get_device_info(self) -> Dict[str, Any]:
        """Get device information."""
        return {
            "identifiers": {("mi_kettle_pro", self.mac_address)},
            "name": self.config["name"],
            "model": self.config["model"],
            "manufacturer": self.config["manufacturer"]
        }
