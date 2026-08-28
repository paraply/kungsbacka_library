"""Data update coordinator for Kungsbacka Library."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ArenaApiError, ArenaAuthError, KungsbackaLibraryAPI, Loan
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class KungsbackaLibraryData:
    """Data returned by the coordinator."""

    loans: list[Loan]


class KungsbackaLibraryCoordinator(DataUpdateCoordinator[KungsbackaLibraryData]):
    """Coordinator to fetch library loan data."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        api: KungsbackaLibraryAPI,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.api = api

    async def _async_update_data(self) -> KungsbackaLibraryData:
        """Fetch loans from the API."""
        try:
            loans = await self.api.async_get_loans()
        except ArenaAuthError as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except ArenaApiError as err:
            raise UpdateFailed(f"Error fetching loans: {err}") from err

        return KungsbackaLibraryData(loans=loans)
