"""Sensor platform for Kungsbacka Library."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_LIBRARY_CARD, DOMAIN
from .coordinator import KungsbackaLibraryCoordinator, KungsbackaLibraryData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    coordinator: KungsbackaLibraryCoordinator = entry.runtime_data
    card_number = entry.data[CONF_LIBRARY_CARD]

    async_add_entities(
        [
            KungsbackaLoanCountSensor(coordinator, entry, card_number),
            KungsbackaOverdueSensor(coordinator, entry, card_number),
            KungsbackaNextDueDateSensor(coordinator, entry, card_number),
        ]
    )


class KungsbackaLibrarySensorBase(
    CoordinatorEntity[KungsbackaLibraryCoordinator], SensorEntity
):
    """Base class for Kungsbacka Library sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: KungsbackaLibraryCoordinator,
        entry: ConfigEntry,
        card_number: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        masked = f"*{card_number[-4:]}" if len(card_number) > 4 else card_number
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, card_number)},
            name=f"Kungsbacka Library ({masked})",
            manufacturer="Kungsbacka kommun",
            model="Axiell Arena",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def _data(self) -> KungsbackaLibraryData | None:
        return self.coordinator.data


class KungsbackaLoanCountSensor(KungsbackaLibrarySensorBase):
    """Sensor showing the total number of active loans."""

    _attr_translation_key = "active_loans"
    _attr_icon = "mdi:book-open-variant"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "loans"

    def __init__(
        self,
        coordinator: KungsbackaLibraryCoordinator,
        entry: ConfigEntry,
        card_number: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, card_number)
        self._attr_unique_id = f"{card_number}_active_loans"

    @property
    def native_value(self) -> int | None:
        """Return the number of active loans."""
        if self._data is None:
            return None
        return len(self._data.loans)

    @property
    def extra_state_attributes(self) -> dict | None:
        """Return loan details as attributes."""
        if self._data is None:
            return None
        return {
            "loans": [loan.as_dict() for loan in self._data.loans],
        }


class KungsbackaOverdueSensor(KungsbackaLibrarySensorBase):
    """Sensor showing the number of overdue loans."""

    _attr_translation_key = "overdue_loans"
    _attr_icon = "mdi:book-alert"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "loans"

    def __init__(
        self,
        coordinator: KungsbackaLibraryCoordinator,
        entry: ConfigEntry,
        card_number: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, card_number)
        self._attr_unique_id = f"{card_number}_overdue_loans"

    @property
    def native_value(self) -> int | None:
        """Return the number of overdue loans."""
        if self._data is None:
            return None
        return sum(1 for loan in self._data.loans if loan.is_overdue)


class KungsbackaNextDueDateSensor(KungsbackaLibrarySensorBase):
    """Sensor showing the next due date across all loans."""

    _attr_translation_key = "next_due_date"
    _attr_icon = "mdi:calendar-clock"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self,
        coordinator: KungsbackaLibraryCoordinator,
        entry: ConfigEntry,
        card_number: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, card_number)
        self._attr_unique_id = f"{card_number}_next_due_date"

    @property
    def native_value(self) -> datetime | None:
        """Return the soonest due date."""
        if self._data is None:
            return None
        due_dates = [
            loan.due_date for loan in self._data.loans if loan.due_date is not None
        ]
        if not due_dates:
            return None
        return min(due_dates)

    @property
    def extra_state_attributes(self) -> dict | None:
        """Return the title of the next due book."""
        if self._data is None or not self._data.loans:
            return None
        due_loans = [l for l in self._data.loans if l.due_date is not None]
        if not due_loans:
            return None
        next_loan = min(due_loans, key=lambda l: l.due_date)  # type: ignore[arg-type]
        return {
            "title": next_loan.title,
            "author": next_loan.author,
            "branch": next_loan.branch,
        }
