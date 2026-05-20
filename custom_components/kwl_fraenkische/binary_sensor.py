"""Binary Sensor-Entities fuer die KWL-Lueeftungsanlage."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import KWLConfigEntry

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import KWLCoordinator, KWLData

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class KWLBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[KWLData], bool | None] = lambda d: None


BINARY_SENSORS: tuple[KWLBinarySensorDescription, ...] = (
    KWLBinarySensorDescription(
        key="filter_ok",
        name="Filter OK",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda d: not d.filter_ok,
    ),
    KWLBinarySensorDescription(
        key="safety_active",
        name="Safety Manager",
        device_class=BinarySensorDeviceClass.SAFETY,
        value_fn=lambda d: d.safety_active,
    ),
    KWLBinarySensorDescription(
        key="passive_mode",
        name="Passivhaus-Modus",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda d: d.passive_mode,
    ),
    KWLBinarySensorDescription(
        key="preheater_active",
        name="Vorheizregister aktiv",
        device_class=BinarySensorDeviceClass.HEAT,
        value_fn=lambda d: d.preheater_active,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KWLConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: KWLCoordinator = entry.runtime_data
    mac = entry.data.get("mac", entry.entry_id)
    async_add_entities(
        KWLBinarySensor(coordinator, entry, description, mac)
        for description in BINARY_SENSORS
    )


class KWLBinarySensor(CoordinatorEntity[KWLCoordinator], BinarySensorEntity):
    """Binaerer Sensor aus der KWL-Anlage."""

    _attr_has_entity_name = True
    entity_description: KWLBinarySensorDescription

    def __init__(
        self,
        coordinator: KWLCoordinator,
        entry: ConfigEntry,
        description: KWLBinarySensorDescription,
        mac: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{mac}_{description.key}"
        self._attr_device_info = coordinator.device_info

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.coordinator.data is not None

    @property
    def is_on(self) -> bool | None:
        """None wenn unavailable -- HA zeigt Entity dann als unavailable an."""
        if not self.available:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
