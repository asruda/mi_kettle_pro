"""Config flow for Mi Kettle Pro integration."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
import homeassistant.helpers.selector as selector

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_MAC
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .device_helpers import BT_MULTI_SELECT, DEFAULT_BT_INTERFACE
from .const import (
    DOMAIN,
    CONF_BT_INTERFACE,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TOKEN,
    CONF_POLL_INTERVAL,
    CONF_HEAT_TEMPERATURE,
    CONF_WARM_TEMPERATURE,
    DEFAULT_DEVICE_NAME,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_HEAT_TEMPERATURE,
    DEFAULT_WARM_TEMPERATURE,
    MIN_HEAT_TEMPERATURE,
    MAX_HEAT_TEMPERATURE,
    MIN_WARM_TEMPERATURE,
    MAX_WARM_TEMPERATURE,
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(
            CONF_BT_INTERFACE,
            default=[DEFAULT_BT_INTERFACE],
        ): cv.multi_select(BT_MULTI_SELECT),
        vol.Required(CONF_MAC): str,
        vol.Required(CONF_DEVICE_TOKEN): str,
        vol.Required(CONF_DEVICE_NAME, default=DEFAULT_DEVICE_NAME): str,
        vol.Required(
            CONF_HEAT_TEMPERATURE, default=DEFAULT_HEAT_TEMPERATURE
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=MIN_HEAT_TEMPERATURE,
                max=MAX_HEAT_TEMPERATURE,
                step=1,
                mode=selector.NumberSelectorMode.BOX
            )
        ),
        vol.Required(
            CONF_WARM_TEMPERATURE, default=DEFAULT_WARM_TEMPERATURE
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=MIN_WARM_TEMPERATURE,
                max=MAX_WARM_TEMPERATURE,
                step=1,
                mode=selector.NumberSelectorMode.BOX
            )
        ),
        vol.Optional(
            CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL
        ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
        # vol.Optional(
        #     CONF_TEMPERATURE_UNIT,
        #     default=DEFAULT_TEMPERATURE_UNIT
        # ): vol.In(TEMPERATURE_UNITS),
    }
)

def validate_device_token(token: str) -> bool:
    """Validate device token format.

    Args:
        token: The device token string to validate

    Returns:
        bool: True if token is valid, False otherwise
    """
    # Check length is exactly 24 characters
    if len(token) != 24:
        return False

    # Check if string contains only hexadecimal characters
    if not re.fullmatch(r"[0-9a-fA-F]{24}", token):
        return False

    # Try to convert to bytes to ensure it's valid hex
    try:
        bytes.fromhex(token)
        return True
    except ValueError:
        return False


class MiKettleProConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mi Kettle Pro."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate the input
            bt_interface = user_input[CONF_BT_INTERFACE]
            mac = user_input[CONF_MAC].replace(":", "").replace("-", "").upper()
            if len(bt_interface) == 0:
                errors["base"] = "Please configure Bluetooth Interface"
            elif len(mac) != 12:
                errors["base"] = "invalid_mac_format"
            elif not validate_device_token(user_input[CONF_DEVICE_TOKEN]):
                errors["base"] = "invalid_device_token_format"
            else:
                # Check if device is already configured
                await self.async_set_unique_id(mac)
                self._abort_if_unique_id_configured()

                # Create the config entry
                return self.async_create_entry(
                    title=self.get_entry_name(),
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            last_step=False
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> MiKettleProOptionsFlow:
        """Get the options flow for this handler."""
        return MiKettleProOptionsFlow()

    def get_entry_name(self):
        # Get current device count to generate default device name
        current_entries = self._async_current_entries()
        device_count = len(current_entries) + 1
        default_device_name = f"Kettle #{device_count}"
        return default_device_name


class MiKettleProOptionsFlow(OptionsFlow):
    """Handle options flow for Mi Kettle Pro."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        data = self.config_entry.data
        options = self.config_entry.options
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate the input
            bt_interface = user_input[CONF_BT_INTERFACE] 
            if len(bt_interface) == 0:
                errors["base"] = "Please configure Bluetooth Interface"
            elif (
                user_input[CONF_POLL_INTERVAL] < 10
                or user_input[CONF_POLL_INTERVAL] > 300
            ):
                errors["base"] = "invalid_poll_interval"
            elif (
                user_input[CONF_HEAT_TEMPERATURE] < MIN_HEAT_TEMPERATURE
                or user_input[CONF_HEAT_TEMPERATURE] > MAX_HEAT_TEMPERATURE
            ):
                errors["base"] = "invalid_heat_temperature"
            elif (
                user_input[CONF_WARM_TEMPERATURE] < MIN_WARM_TEMPERATURE
                or user_input[CONF_WARM_TEMPERATURE] > MAX_WARM_TEMPERATURE
            ):
                errors["base"] = "invalid_warm_temperature"
            elif not validate_device_token(user_input[CONF_DEVICE_TOKEN]):
                errors["base"] = "invalid_device_token_format"
            else:
                new_data = {**self.config_entry.data, **user_input}
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=new_data,
                )

                # Update the options
                return self.async_create_entry(data=options)

        default_bt_interface_value = data.get(
                        CONF_BT_INTERFACE, [DEFAULT_BT_INTERFACE]
                    )
        for index, item in enumerate(default_bt_interface_value):
            if item == "disable":
                del default_bt_interface_value[index]

        options_schema = vol.Schema(
            {
                vol.Required(
                    CONF_BT_INTERFACE,
                    default=default_bt_interface_value,
                ): cv.multi_select(BT_MULTI_SELECT),
                vol.Required(
                    CONF_DEVICE_TOKEN,
                    default=data.get(CONF_DEVICE_TOKEN, ""),
                ): str,
                vol.Optional(
                    CONF_POLL_INTERVAL,
                    default=data.get(
                        CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
                # vol.Optional(
                #     CONF_TEMPERATURE_UNIT,
                #     default=self.data.get(
                #         CONF_TEMPERATURE_UNIT, DEFAULT_TEMPERATURE_UNIT
                #     ),
                # ): vol.In(TEMPERATURE_UNITS),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
            errors=errors,
        )
