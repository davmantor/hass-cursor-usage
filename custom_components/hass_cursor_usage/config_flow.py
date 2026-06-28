"""Config flow for Cursor Usage integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from .auth import AuthFileError, read_auth_file
from .const import (
    CONF_AUTH_FILE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_AUTH_FILE,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


def _validate_auth_file(path: str) -> str | None:
    """Validate a Cursor auth file path.

    Returns:
        ``"auth_file_unreadable"`` – the file is missing, unreadable, or not a
        JSON object.
        ``"missing_refresh_token"`` – the file is valid JSON but has no
        ``refresh_token`` field.
        ``None`` – the file is valid and contains a refresh token.
    """
    try:
        auth = read_auth_file(path)
    except AuthFileError:
        return "auth_file_unreadable"

    if not auth.refresh_token:
        return "missing_refresh_token"

    return None


class CursorUsageConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cursor Usage."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            auth_file = user_input[CONF_AUTH_FILE].strip()
            error = await self.hass.async_add_executor_job(_validate_auth_file, auth_file)

            if error is not None:
                errors[CONF_AUTH_FILE] = error
            else:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Cursor Usage",
                    data={CONF_AUTH_FILE: auth_file},
                    options={CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_AUTH_FILE, default=DEFAULT_AUTH_FILE): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow."""
        return CursorUsageOptionsFlow()


class CursorUsageOptionsFlow(OptionsFlow):
    """Handle options for Cursor Usage."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_UPDATE_INTERVAL, default=current_interval): vol.All(
                        int, vol.Range(min=MIN_UPDATE_INTERVAL, max=MAX_UPDATE_INTERVAL)
                    ),
                }
            ),
        )
