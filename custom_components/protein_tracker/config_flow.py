"""Config flow for Protein Tracker."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_GOAL,
    CONF_ID,
    CONF_NAME,
    DEFAULT_GOAL,
    DOMAIN,
)
from .naming import tracker_display_name


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Protein Tracker."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        if user_input is not None:
            tracker_id = str(user_input[CONF_ID])
            await self.async_set_unique_id(tracker_id)
            self._abort_if_unique_id_configured()

            base_name = str(user_input.get(CONF_NAME, tracker_id)).strip() or tracker_id
            title = tracker_display_name(base_name)
            return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ID): cv.slug,
                    vol.Required(CONF_NAME): str,
                    vol.Required(CONF_GOAL, default=DEFAULT_GOAL): vol.Coerce(float),
                }
            ),
        )

    async def async_step_import(self, user_input: dict[str, Any]):
        """Handle import from YAML."""
        tracker_id = str(user_input[CONF_ID])
        await self.async_set_unique_id(tracker_id)
        self._abort_if_unique_id_configured(updates=user_input)

        base_name = str(user_input.get(CONF_NAME, tracker_id)).strip() or tracker_id
        title = tracker_display_name(base_name)
        return self.async_create_entry(title=title, data=user_input)
