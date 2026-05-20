"""Sensor-Entities fuer die KWL-Lueeftungsanlage."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import KWLConfigEntry

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
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

from .const import DOMAIN, LEVEL_TO_WATT
from .coordinator import KWLCoordinator, KWLData

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class KWLSensorDescription(SensorEntityDescription):
    value_fn: Callable[[KWLData], float | int | str | None] = lambda d: None
    # force_update pro Sensor steuerbar -- True fuer Messwerte die sich
    # selten aendern aber trotzdem lueckenlos im Recorder landen sollen
    force_update: bool = False


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
        name="Aussenluft Temperatur",
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
        name="Zuluft Motor U/min",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        force_update=True,
        value_fn=lambda d: d.motor_zuluft_rpm,
    ),
    KWLSensorDescription(
        key="motor_abluft_rpm",
        name="Abluft Motor U/min",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        force_update=True,
        value_fn=lambda d: d.motor_abluft_rpm,
    ),
    KWLSensorDescription(
        key="motor_zuluft_volt",
        name="Zuluft Motor Spannung",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        value_fn=lambda d: d.motor_zuluft_volt,
    ),
    KWLSensorDescription(
        key="motor_abluft_volt",
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
        name="Betriebsstunden Stufe 1",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.hours_level_1,
    ),
    KWLSensorDescription(
        key="hours_level_2",
        name="Betriebsstunden Stufe 2",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.hours_level_2,
    ),
    KWLSensorDescription(
        key="hours_level_3",
        name="Betriebsstunden Stufe 3",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.hours_level_3,
    ),
    KWLSensorDescription(
        key="hours_level_4",
        name="Betriebsstunden Stufe 4",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.hours_level_4,
    ),
    KWLSensorDescription(
        key="hours_frost",
        name="Betriebsstunden Frostschutz",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.hours_frost,
    ),
    KWLSensorDescription(
        key="hours_preheater",
        name="Betriebsstunden Vorheizregister",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.hours_preheater,
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
        name="Systemmeldung",
        value_fn=lambda d: d.system_message,
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
        KWLSensor(coordinator, entry, description, mac) for description in SENSORS
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
        value = self.entity_description.value_fn(self.coordinator.data)
        # Watt-abhaengige Sensoren neu berechnen mit konfigurierten Watt-Werten
        key = self.entity_description.key
        watt_map = self.coordinator.watt_map
        if key == "power_current":
            return watt_map.get(self.coordinator.data.current_level)
        if key.startswith("energy_level_"):
            level = int(key[-1])
            hours = getattr(self.coordinator.data, f"hours_level_{level}", None)
            if hours is None:
                return None
            return round(hours * watt_map[level] / 1000, 2)
        return value
