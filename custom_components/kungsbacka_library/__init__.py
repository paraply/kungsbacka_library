"""The Kungsbacka Library integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .api import KungsbackaLibraryAPI
from .const import CONF_LIBRARY_CARD, CONF_PIN, DOMAIN
from .coordinator import KungsbackaLibraryCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

type KungsbackaLibraryConfigEntry = ConfigEntry[KungsbackaLibraryCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: KungsbackaLibraryConfigEntry
) -> bool:
    """Set up Kungsbacka Library from a config entry."""
    api = KungsbackaLibraryAPI(
        card_number=entry.data[CONF_LIBRARY_CARD],
        pin=entry.data[CONF_PIN],
    )

    coordinator = KungsbackaLibraryCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: KungsbackaLibraryConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
