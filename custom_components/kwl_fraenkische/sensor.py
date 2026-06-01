"""Sensor-Entities fuer die KWL-Lüftungsanlage."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import KWLConfigEntry

from dataclasses import dataclass, field
from typing import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import EntityCategory
from homeassistant.const import (
    UnitOfEnergy,
    UnitOfElectricPotential,
    UnitOfTemperature,
    UnitOfTime,
    REVOLUTIONS_PER_MINUTE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ENDPOINT_INSTALL, ENDPOINT_WOPLA, LEVEL_TO_WATT
from .coordinator import KWLCapabilities, KWLCoordinator, KWLData, _is_supported

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class KWLSensorDescription(SensorEntityDescription):
    value_fn: Callable[[KWLData], float | int | str | None] = lambda d: None
    # force_update pro Sensor steuerbar -- True fuer Messwerte die sich
    # selten aendern aber trotzdem lueckenlos im Recorder landen sollen
    force_update: bool = False
    required_tag: str | None = field(default=None)
    required_endpoint: str | None = field(default=None)
    entity_category: EntityCategory | None = field(default=None)


def _energy_kwh(hours: int | None, watt: float) -> float | None:
    if hours is None:
        return None
    return round(hours * watt / 1000, 2)


SENSORS: tuple[KWLSensorDescription, ...] = (

    # ------------------------------------------------------------------
    # Temperaturen -- force_update=True damit der Recorder bei jedem
    # Poll einen Eintrag schreibt, auch wenn der Wert gleich bleibt.
    # Ohne das erscheinen Temperaturkurven im Graph flach.
    # ------------------------------------------------------------------
    KWLSensorDescription(
        key="temp_abluft",
        name="Abluft Temperatur",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        force_update=True,
        value_fn=lambda d: d.temp_abluft,
    ),
    KWLSensorDescription(
        key="temp_zuluft",
        name="Zuluft Temperatur",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        force_update=True,
        value_fn=lambda d: d.temp_zuluft,
    ),
    KWLSensorDescription(
        key="temp_aussenluft",
        name="Außenluft Temperatur",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        force_update=True,
        value_fn=lambda d: d.temp_aussenluft,
    ),
    KWLSensorDescription(
        key="temp_fortluft",
        name="Fortluft Temperatur",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        force_update=True,
        value_fn=lambda d: d.temp_fortluft,
    ),

    # ------------------------------------------------------------------
    # Motorstatus -- force_update=True fuer RPM (aendert sich graduell)
    # ------------------------------------------------------------------
    KWLSensorDescription(
        key="motor_zuluft_rpm",
        entity_category=EntityCategory.DIAGNOSTIC,
        required_tag="MoStZlUm",
        name="Zuluft Motor U/min",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        force_update=True,
        value_fn=lambda d: d.motor_zuluft_rpm,
    ),
    KWLSensorDescription(
        key="motor_abluft_rpm",
        entity_category=EntityCategory.DIAGNOSTIC,
        required_tag="MoStAlUm",
        name="Abluft Motor U/min",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        force_update=True,
        value_fn=lambda d: d.motor_abluft_rpm,
    ),
    KWLSensorDescription(
        key="motor_zuluft_volt",
        entity_category=EntityCategory.DIAGNOSTIC,
        required_tag="MoStZlVo",
        name="Zuluft Motor Spannung",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        value_fn=lambda d: d.motor_zuluft_volt,
    ),
    KWLSensorDescription(
        key="motor_abluft_volt",
        entity_category=EntityCategory.DIAGNOSTIC,
        required_tag="MoStAlVo",
        name="Abluft Motor Spannung",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        value_fn=lambda d: d.motor_abluft_volt,
    ),

    # ------------------------------------------------------------------
    # Aktuelle Leistung -- kein force_update noetig, aendert sich nur
    # bei Stufenwechsel
    # ------------------------------------------------------------------
    KWLSensorDescription(
        key="power_current",
        name="Aktuelle Leistung",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        value_fn=lambda d: LEVEL_TO_WATT.get(d.current_level),
    ),

    # ------------------------------------------------------------------
    # Kumulativer Energieverbrauch -- TOTAL_INCREASING, kein force_update
    # ------------------------------------------------------------------
    KWLSensorDescription(
        key="energy_level_1",
        name="Energie Stufe 1",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        value_fn=lambda d: _energy_kwh(d.hours_level_1, LEVEL_TO_WATT[1]),
    ),
    KWLSensorDescription(
        key="energy_level_2",
        name="Energie Stufe 2",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        value_fn=lambda d: _energy_kwh(d.hours_level_2, LEVEL_TO_WATT[2]),
    ),
    KWLSensorDescription(
        key="energy_level_3",
        name="Energie Stufe 3",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        value_fn=lambda d: _energy_kwh(d.hours_level_3, LEVEL_TO_WATT[3]),
    ),
    KWLSensorDescription(
        key="energy_level_4",
        name="Energie Stufe 4",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        value_fn=lambda d: _energy_kwh(d.hours_level_4, LEVEL_TO_WATT[4]),
    ),

    # ------------------------------------------------------------------
    # Betriebsstunden (standardmaessig ausgeblendet)
    # ------------------------------------------------------------------
    KWLSensorDescription(
        key="hours_level_1",
        entity_category=EntityCategory.DIAGNOSTIC,
        required_tag="BsSt1",
        name="Betriebsstunden Stufe 1",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.hours_level_1,
    ),
    KWLSensorDescription(
        key="hours_level_2",
        entity_category=EntityCategory.DIAGNOSTIC,
        required_tag="BsSt2",
        name="Betriebsstunden Stufe 2",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.hours_level_2,
    ),
    KWLSensorDescription(
        key="hours_level_3",
        entity_category=EntityCategory.DIAGNOSTIC,
        required_tag="BsSt3",
        name="Betriebsstunden Stufe 3",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.hours_level_3,
    ),
    KWLSensorDescription(
        key="hours_level_4",
        entity_category=EntityCategory.DIAGNOSTIC,
        required_tag="BsSt4",
        name="Betriebsstunden Stufe 4",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.hours_level_4,
    ),
    # ------------------------------------------------------------------
    # Filter Restlaufzeit -- aus der anderen Integration uebernommen
    # ------------------------------------------------------------------
    KWLSensorDescription(
        key="filter_total_days",
        entity_category=EntityCategory.DIAGNOSTIC,
        required_tag="filtertime",
        name="Filter Gesamtlaufzeit",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.DAYS,
        icon="mdi:air-filter",
        value_fn=lambda d: d.filter_total_days,
    ),
    KWLSensorDescription(
        key="filter_residual_days",
        entity_category=EntityCategory.DIAGNOSTIC,
        required_tag="rest_time",
        name="Filter Restlaufzeit",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.DAYS,
        icon="mdi:air-filter",
        value_fn=lambda d: d.filter_residual_days,
    ),

    KWLSensorDescription(
        key="hours_frost",
        entity_category=EntityCategory.DIAGNOSTIC,
        required_tag="BsFs",
        name="Betriebsstunden Frostschutz",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.hours_frost,
    ),
    KWLSensorDescription(
        key="hours_preheater",
        entity_category=EntityCategory.DIAGNOSTIC,
        required_tag="BsVhr",
        name="Betriebsstunden Vorheizregister",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.hours_preheater,
    ),

    # ------------------------------------------------------------------
    # Derived / Diagnostic Sensoren -- berechnet aus Geraetedaten
    # ------------------------------------------------------------------
    KWLSensorDescription(
        key="heat_recovery_efficiency",
        name="Waermerueckgewinnungsgrad",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        suggested_display_precision=1,
        icon="mdi:heat-wave",
        force_update=True,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.heat_recovery_efficiency,
    ),
    KWLSensorDescription(
        key="heat_recovery_watts",
        name="Rueckgewonnene Waermeleistung",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W",
        suggested_display_precision=0,
        force_update=True,
        value_fn=lambda d: d.heat_recovery_watts,
    ),

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    KWLSensorDescription(
        key="current_level_text",
        name="Aktuelle Stufe",
        value_fn=lambda d: d.current_level_text,
    ),
    KWLSensorDescription(
        key="party_timer",
        name="Party-Timer Restzeit",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda d: d.party_timer_minutes,
    ),
    KWLSensorDescription(
        key="bypass_status",
        name="Bypass Status",
        value_fn=lambda d: d.bypass_status,
    ),
    KWLSensorDescription(
        key="system_message",
        entity_category=EntityCategory.DIAGNOSTIC,
        name="Systemmeldung",
        value_fn=lambda d: d.system_message,
    ),
)



class KWLSensor(CoordinatorEntity[KWLCoordinator], SensorEntity):
    """Einzelner Sensor aus der KWL-Anlage."""

    _attr_has_entity_name = True
    entity_description: KWLSensorDescription

    def __init__(
        self,
        coordinator: KWLCoordinator,
        entry: ConfigEntry,
        description: KWLSensorDescription,
        mac: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{mac}_{description.key}"
        self._attr_device_info = coordinator.device_info
        # force_update aus der Description uebernehmen
        self._attr_force_update = description.force_update

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.coordinator.data is not None

    @property
    def native_value(self) -> float | int | str | None:
        if not self.available:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class KWLWattSensor(KWLSensor):
    """Sensor der den konfigurierten watt_map-Wert des Coordinators nutzt."""

    @property
    def native_value(self) -> float | int | str | None:
        if not self.available:
            return None
        key = self.entity_description.key
        watt_map = self.coordinator.watt_map
        if key == "power_current":
            result: float | None = watt_map.get(self.coordinator.data.current_level)
            return result
        if key.startswith("energy_level_"):
            level = int(key[-1])
            hours = getattr(self.coordinator.data, f"hours_level_{level}", None)
            if hours is None:
                return None
            return float(round(hours * watt_map[level] / 1000, 2))
        return self.entity_description.value_fn(self.coordinator.data)


_WATT_SENSOR_KEYS = frozenset({
    "power_current",
    "energy_level_1", "energy_level_2", "energy_level_3", "energy_level_4",
})


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KWLConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: KWLCoordinator = entry.runtime_data
    mac = entry.data.get("mac", entry.entry_id)
    caps = coordinator.capabilities
    supported = [d for d in SENSORS if caps is None or _is_supported(d, caps)]
    entities = []
    for desc in supported:
        cls = KWLWattSensor if desc.key in _WATT_SENSOR_KEYS else KWLSensor
        entities.append(cls(coordinator, entry, desc, mac))
    async_add_entities(entities)
