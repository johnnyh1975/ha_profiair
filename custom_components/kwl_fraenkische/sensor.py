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

from .const import CONF_PROTOCOL, DOMAIN, ENDPOINT_INSTALL, ENDPOINT_WOPLA, LEVEL_TO_WATT, PROTOCOL_HTTP, PROTOCOL_MODBUS
from .coordinator import KWLCapabilities, KWLCoordinator, KWLData, _is_supported

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class KWLSensorDescription(SensorEntityDescription):
    value_fn: Callable[[KWLData], float | int | str | None] = lambda d: None
    force_update: bool = False
    required_tag: str | None = field(default=None)
    required_endpoint: str | None = field(default=None)
    entity_category: EntityCategory | None = field(default=None)
    # None = beide Protokolle, {PROTOCOL_HTTP} = nur touch, {PROTOCOL_MODBUS} = nur flex
    supported_protocols: frozenset[str] | None = field(default=None)


@dataclass(frozen=True, kw_only=True)
class KWLAnalyticsSensorDescription(SensorEntityDescription):
    """Description for sensors backed by KWLAnalytics."""
    value_fn: Callable[[KWLCoordinator], float | int | str | None] = lambda c: None
    entity_category: EntityCategory | None = field(default=EntityCategory.DIAGNOSTIC)
    # Analytics-Sensoren sind aktuell touch-only (Baselines noch nicht für flex kalibriert)
    supported_protocols: frozenset[str] | None = field(default=frozenset({PROTOCOL_HTTP}))


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
        supported_protocols=frozenset({PROTOCOL_HTTP}),
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
        supported_protocols=frozenset({PROTOCOL_HTTP}),
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
        supported_protocols=frozenset({PROTOCOL_HTTP}),
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
        supported_protocols=frozenset({PROTOCOL_HTTP}),
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
        supported_protocols=frozenset({PROTOCOL_HTTP}),
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
        supported_protocols=frozenset({PROTOCOL_HTTP}),
    ),
    KWLSensorDescription(
        key="energy_level_2",
        name="Energie Stufe 2",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        value_fn=lambda d: _energy_kwh(d.hours_level_2, LEVEL_TO_WATT[2]),
        supported_protocols=frozenset({PROTOCOL_HTTP}),
    ),
    KWLSensorDescription(
        key="energy_level_3",
        name="Energie Stufe 3",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        value_fn=lambda d: _energy_kwh(d.hours_level_3, LEVEL_TO_WATT[3]),
        supported_protocols=frozenset({PROTOCOL_HTTP}),
    ),
    KWLSensorDescription(
        key="energy_level_4",
        name="Energie Stufe 4",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        value_fn=lambda d: _energy_kwh(d.hours_level_4, LEVEL_TO_WATT[4]),
        supported_protocols=frozenset({PROTOCOL_HTTP}),
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
        supported_protocols=frozenset({PROTOCOL_HTTP}),
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
        supported_protocols=frozenset({PROTOCOL_HTTP}),
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
        supported_protocols=frozenset({PROTOCOL_HTTP}),
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
        supported_protocols=frozenset({PROTOCOL_HTTP}),
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
        supported_protocols=frozenset({PROTOCOL_HTTP}),
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
        supported_protocols=frozenset({PROTOCOL_HTTP}),
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
        supported_protocols=frozenset({PROTOCOL_HTTP}),
    ),
    KWLSensorDescription(
        key="party_timer",
        name="Party-Timer Restzeit",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda d: d.party_timer_minutes,
        supported_protocols=frozenset({PROTOCOL_HTTP}),
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
        supported_protocols=frozenset({PROTOCOL_HTTP}),
    ),

    # ── Flex-only Sensoren (profi-air 250/360 flex, 180 flat) ─────────────
    KWLSensorDescription(
        key="current_mode_text",
        name="Betriebsmodus",
        icon="mdi:cog",
        value_fn=lambda d: d.current_mode_text,
        supported_protocols=frozenset({PROTOCOL_MODBUS}),
    ),
    KWLSensorDescription(
        key="alarm_text",
        name="Alarm",
        icon="mdi:alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.alarm_text,
        supported_protocols=frozenset({PROTOCOL_MODBUS}),
    ),
    KWLSensorDescription(
        key="preheater_duty_pct",
        name="Vorheizregister Auslastung",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.preheater_duty_pct,
        supported_protocols=frozenset({PROTOCOL_MODBUS}),
    ),
    KWLSensorDescription(
        key="hours_total",
        name="Gesamtbetriebsstunden",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.hours_total,
        supported_protocols=frozenset({PROTOCOL_MODBUS}),
    ),
    KWLSensorDescription(
        key="bypass_tmin",
        name="Bypass Mindesttemperatur",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement="°C",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.bypass_tmin,
        supported_protocols=frozenset({PROTOCOL_MODBUS}),
    ),
    KWLSensorDescription(
        key="bypass_tmax",
        name="Bypass Maximaltemperatur",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement="°C",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.bypass_tmax,
        supported_protocols=frozenset({PROTOCOL_MODBUS}),
    ),
    KWLSensorDescription(
        key="temp_room",
        name="Raumtemperatur",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="°C",
        value_fn=lambda d: d.temp_room,
        supported_protocols=frozenset({PROTOCOL_MODBUS}),
    ),
    KWLSensorDescription(
        key="voc_ppm",
        name="VOC",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="ppm",
        icon="mdi:molecule",
        value_fn=lambda d: d.voc_ppm,
        supported_protocols=frozenset({PROTOCOL_MODBUS}),
    ),
    KWLSensorDescription(
        key="rh_percent",
        name="Relative Feuchte",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        value_fn=lambda d: d.rh_percent,
        supported_protocols=frozenset({PROTOCOL_MODBUS}),
    ),
    KWLSensorDescription(
        key="co2_ppm",
        name="CO₂",
        device_class=SensorDeviceClass.CO2,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="ppm",
        value_fn=lambda d: d.co2_ppm,
        supported_protocols=frozenset({PROTOCOL_MODBUS}),
    ),
    KWLSensorDescription(
        key="motor_abluft_rpm_flex",
        name="Abluft-Ventilator RPM",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.motor_abluft_rpm,
        supported_protocols=frozenset({PROTOCOL_MODBUS}),
    ),
    KWLSensorDescription(
        key="motor_zuluft_rpm_flex",
        name="Zuluft-Ventilator RPM",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.motor_zuluft_rpm,
        supported_protocols=frozenset({PROTOCOL_MODBUS}),
    ),
)

# ── Analytics-backed sensors ──────────────────────────────────────────────────
# Backed by KWLAnalytics; always added (not capability-gated).
# Disabled by default until baselines are established.

ANALYTICS_SENSORS: tuple[KWLAnalyticsSensorDescription, ...] = (
    # Bypass statistics
    KWLAnalyticsSensorDescription(
        key="bypass_open_pct",
        name="Bypass Offen-Anteil",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        suggested_display_precision=1,
        icon="mdi:valve-open",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.analytics.bypass_open_pct if c.analytics else None,
    ),
    KWLAnalyticsSensorDescription(
        key="bypass_avg_open_min",
        name="Bypass Ø Offen-Dauer",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        icon="mdi:timer-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.analytics.avg_bypass_open_min if c.analytics else None,
    ),
    KWLAnalyticsSensorDescription(
        key="bypass_transitions_1h",
        name="Bypass Wechsel letzte Stunde",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="",
        icon="mdi:valve-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.analytics.bypass_transitions_1h if c.analytics else None,
    ),
    # Night cooling
    # Standardmäßig deaktiviert: zeigt "Unbekannt" bis das erste qualifizierende
    # Nachtkühlungs-Ereignis aufgetreten ist (Stufe 4 + messbarer T_Abluft-Abfall).
    # Kann je nach Klima/Dämmung Wochen dauern. Nutzer kann manuell aktivieren
    # sobald Interesse an diesem Wert besteht.
    KWLAnalyticsSensorDescription(
        key="night_cooling_last_k",
        name="Nachtlueftung letzter Kuehlerfolg",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="K",
        suggested_display_precision=1,
        icon="mdi:weather-night",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.analytics.night_cooling_last_k if c.analytics else None,
    ),
    KWLAnalyticsSensorDescription(
        key="night_cooling_7d_avg_k",
        name="Nachtlueftung Ø 7 Tage",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="K",
        suggested_display_precision=1,
        icon="mdi:weather-night",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.analytics.night_cooling_7d_avg_k if c.analytics else None,
    ),
    # HRE analytics
    KWLAnalyticsSensorDescription(
        key="eps_exhaust",
        name="WRG Abluftseite",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        suggested_display_precision=1,
        icon="mdi:heat-wave",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.analytics.eps_exhaust_pct if c.analytics else None,
    ),
    KWLAnalyticsSensorDescription(
        key="energy_balance_ratio",
        name="Energiebilanz-Verhaeltnis",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="",
        suggested_display_precision=3,
        icon="mdi:scale-balance",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.analytics.energy_balance_ratio if c.analytics else None,
    ),
    # RPM analytics
    KWLAnalyticsSensorDescription(
        key="rpm_ratio",
        name="Motor RPM Verhaeltnis",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="",
        suggested_display_precision=4,
        icon="mdi:fan",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.analytics.current_rpm_ratio if c.analytics else None,
    ),
    # Analytics maturity
    KWLAnalyticsSensorDescription(
        key="analytics_maturity",
        name="Analytics Reifegrad",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        suggested_display_precision=0,
        icon="mdi:chart-timeline-variant",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=True,
        value_fn=lambda c: c.analytics.analytics_maturity_pct if c.analytics else None,
    ),
    # Season
    KWLAnalyticsSensorDescription(
        key="analytics_season",
        name="Analytics Saison",
        icon="mdi:calendar-month",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.analytics.season if c.analytics else None,
    ),
    # Fan law consistency — max residual across all levels vs two-parameter EC model
    # Threshold: 5% of P_Stufe4 = 4W → genuine fault detection, not motor overhead artefact
    KWLAnalyticsSensorDescription(
        key="fan_law_max_deviation",
        name="EC-Modell Max-Abweichung",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        suggested_display_precision=1,
        icon="mdi:fan-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: (
            round(max(abs(v) for v in c.fan_law_consistency.values()), 1)
            if c.fan_law_consistency else None
        ),
    ),
    # SPI reference sensor (Stufe 4 — the most meaningful for cross-comparison)
    KWLAnalyticsSensorDescription(
        key="spi_stufe4",
        name="Spezifischer Leistungseintrag Stufe 4",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="W/(m³/h)",
        suggested_display_precision=4,
        icon="mdi:lightning-bolt",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: (c.spi_per_level or {}).get(4),
    ),
)


_WATT_SENSOR_KEYS = frozenset({
    "power_current",
    "energy_level_1", "energy_level_2", "energy_level_3", "energy_level_4",
})



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
        # Activate translation lookup from strings.json / translations/*.json
        if not description.translation_key:
            self._attr_translation_key = description.key
        self.entity_id = f"sensor.{coordinator.model_slug}_{description.key}"

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.coordinator.data is not None

    @property
    def native_value(self) -> float | int | str | None:
        if not self.available:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class KWLWattSensor(KWLSensor):
    """Sensor fuer Leistungs- und Energieberechnung.

    power_current: Dynamisch aus Motordrehzahl (Fanlaufgesetz P ∝ n³).
                   Gibt kontinuierliche Werte auch zwischen Stufen.
                   Referenzpunkt: konfigurierte Stufe-4-Leistung + RPM-Baseline.

    energy_level_X: Statisch aus watt_map × Betriebsstunden.
                    Stufen-Watt-Werte werden fuer Energieakkumulation benoetigt.
    """

    @property
    def native_value(self) -> float | int | str | None:
        if not self.available:
            return None
        key = self.entity_description.key
        watt_map = self.coordinator.watt_map

        if key == "power_current":
            rpm_ab = self.coordinator.data.motor_abluft_rpm
            if rpm_ab is not None and rpm_ab > 50:
                # EC-Motor-Zwei-Parameter-Modell: P = P_base + k × (RPM/RPM_ref)³
                # Berücksichtigt ~9 W Festanteil (Steuerelektronik + Mindesterregung).
                # Reines P ∝ n³ würde Stufe 1 um 72 % unterschätzen.
                rpm_ref = self.coordinator.rpm_reference_stufe4
                p_base, k_aero = self.coordinator.motor_power_params
                return round(p_base + k_aero * (rpm_ab / rpm_ref) ** 3, 1)
            return watt_map.get(self.coordinator.data.current_level)

        if key.startswith("energy_level_"):
            level = int(key[-1])
            hours = getattr(self.coordinator.data, f"hours_level_{level}", None)
            if hours is None:
                return None
            return float(round(hours * watt_map[level] / 1000, 2))

        return self.entity_description.value_fn(self.coordinator.data)


class KWLAnalyticsSensor(CoordinatorEntity[KWLCoordinator], SensorEntity):
    """Sensor backed by KWLAnalytics (not raw device data)."""

    _attr_has_entity_name = True
    entity_description: KWLAnalyticsSensorDescription

    def __init__(
        self,
        coordinator: KWLCoordinator,
        entry: ConfigEntry,
        description: KWLAnalyticsSensorDescription,
        mac: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{mac}_{description.key}"
        self._attr_device_info = coordinator.device_info
        if description.entity_category is not None:
            self._attr_entity_category = description.entity_category
        if not description.translation_key:
            self._attr_translation_key = description.key
        self.entity_id = f"sensor.{coordinator.model_slug}_{description.key}"

    @property
    def available(self) -> bool:
        return (
            self.coordinator.last_update_success
            and self.coordinator.analytics is not None
        )

    @property
    def native_value(self) -> float | int | str | None:
        if not self.available:
            return None
        return self.entity_description.value_fn(self.coordinator)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: KWLConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    protocol = entry.data.get(CONF_PROTOCOL, PROTOCOL_HTTP)
    mac = entry.data.get("mac", entry.entry_id)
    entities: list = []

    if protocol == PROTOCOL_MODBUS:
        # Flex-Pfad: required_tag NICHT ausschließen — Tags sind XML-spezifisch (touch-Capability-Gate),
        # aber value_fn kann trotzdem shared Properties (temps, filter_days, bypass) aufrufen.
        # Touch-only Properties sind explizit mit supported_protocols={PROTOCOL_HTTP} markiert.
        supported = [
            d for d in SENSORS
            if (d.supported_protocols is None or PROTOCOL_MODBUS in d.supported_protocols)
            and not d.required_endpoint
        ]
        entities = [KWLSensor(coordinator, entry, desc, mac) for desc in supported]
        # Keine Analytics-Sensoren für flex (Baselines noch nicht kalibriert)
    else:
        # Touch-Pfad: bisheriges Verhalten + Protocol-Filter
        caps = coordinator.capabilities
        supported = [
            d for d in SENSORS
            if (d.supported_protocols is None or PROTOCOL_HTTP in d.supported_protocols)
            and (caps is None or _is_supported(d, caps))
        ]
        for desc in supported:
            cls = KWLWattSensor if desc.key in _WATT_SENSOR_KEYS else KWLSensor
            entities.append(cls(coordinator, entry, desc, mac))
        entities += [
            KWLAnalyticsSensor(coordinator, entry, desc, mac)
            for desc in ANALYTICS_SENSORS
        ]

    async_add_entities(entities)