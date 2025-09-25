"""Utility functions for Mi Kettle Pro integration."""

from homeassistant.config_entries import ConfigEntry


def gen_entity_id(
    entry: ConfigEntry,
    platform_name: str,
    attr_unique_id: str,
) -> str:
    """Generate entity ID for Mi Kettle Pro entities."""
    return (
        f"{platform_name}.{entry.entry_id}_"
        f"{entry.data.get('mac', '').replace(':', '')}_{attr_unique_id}"
    )
