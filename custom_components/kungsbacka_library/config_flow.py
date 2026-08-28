"""Config flow for Kungsbacka Library."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .api import ArenaApiError, ArenaAuthError, KungsbackaLibraryAPI
from .const import CONF_LIBRARY_CARD, CONF_PIN, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_LIBRARY_CARD): str,
        vol.Required(CONF_PIN): str,
    }
)


class KungsbackaLibraryConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Kungsbacka Library."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            card_number = user_input[CONF_LIBRARY_CARD]
            pin = user_input[CONF_PIN]

            # Prevent duplicate entries for the same card
            await self.async_set_unique_id(card_number)
            self._abort_if_unique_id_configured()

            api = KungsbackaLibraryAPI(card_number, pin)

            try:
                valid = await api.async_validate_credentials()
            except ArenaAuthError:
                errors["base"] = "invalid_auth"
            except ArenaApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during config flow")
                errors["base"] = "unknown"
            else:
                if not valid:
                    errors["base"] = "invalid_auth"

            if not errors:
                # Mask card number for the title: show last 4 digits
                masked = f"*{card_number[-4:]}" if len(card_number) > 4 else card_number
                return self.async_create_entry(
                    title=f"Kungsbacka Library ({masked})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
