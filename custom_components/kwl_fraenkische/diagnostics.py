"""Diagnostics fuer die KWL Fraenkische Rohrwerke Integration."""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import KWLConfigEntry
from .const import CONF_PROTOCOL, PROTOCOL_MODBUS, PROTOCOL_REST

REDACTED = "**REDACTED**"


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: KWLConfigEntry,
) -> dict[str, Any]:
    """Diagnosedaten fuer den Download-Diagnose-Dialog in HA.

    Sensitive Daten (Passwort, MAC) werden automatisch geschwärzt.
    Ausgabe ist protokoll-spezifisch (touch vs flex/flat).
    """
    coordinator = entry.runtime_data
    protocol = entry.data.get(CONF_PROTOCOL, "http")

    config_data = dict(entry.data)
    # Nur vorhandene Secrets schwärzen -- ein read-only Touch-Setup hat z.B.
    # gar kein Passwort, dann darf auch kein REDACTED-Key erscheinen.
    for secret_key in ("password", "username", "mac", "serial", "name"):
        if secret_key in config_data:
            config_data[secret_key] = REDACTED

    if protocol == PROTOCOL_REST:
        return _lite_diagnostics(entry, coordinator, config_data)

    data = coordinator.data
    base = {
        "config_entry": config_data,
        "protocol": protocol,
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval else None
            ),
        },
        "options": {
            "scan_interval": entry.options.get("scan_interval", 30),
            "watt_map": coordinator.watt_map,
        },
    }

    if protocol == PROTOCOL_MODBUS:
        # ── Flex / Flat Diagnose ───────────────────────────────────────────────
        caps = coordinator.capabilities
        base["capabilities"] = (
            {
                "model":               caps.model,
                "firmware_version":    caps.firmware_version,
                "fan1_is_extract":     caps.fan1_is_extract,
                "ref_rpm_extract_s3":  caps.ref_rpm_extract_s3,
                "ref_rpm_supply_s3":   caps.ref_rpm_supply_s3,
            }
            if caps else "not_yet_discovered"
        )
        base["device_data"] = {
            "current_level":      data.current_level       if data else None,
            "current_mode":       data.current_mode        if data else None,
            "current_mode_text":  data.current_mode_text   if data else None,
            "alarm_code":         data.alarm_code          if data else None,
            "alarm_text":         data.alarm_text          if data else None,
            "unit_mode_mask":     getattr(data, "unit_mode_mask", None) if data else None,
            "alarm_mask":         getattr(data, "alarm_mask", None)     if data else None,
            "temp_abluft":        data.temp_abluft         if data else None,
            "temp_zuluft":        data.temp_zuluft         if data else None,
            "temp_aussenluft":    data.temp_aussenluft     if data else None,
            "temp_fortluft":      data.temp_fortluft       if data else None,
            "temp_room":          data.temp_room           if data else None,
            "motor_abluft_rpm":   data.motor_abluft_rpm    if data else None,
            "motor_zuluft_rpm":   data.motor_zuluft_rpm    if data else None,
            "bypass_status":      data.bypass_status       if data else None,
            "filter_ok":          data.filter_ok           if data else None,
            "filter_residual_days": data.filter_residual_days if data else None,
            "preheater_duty_pct": data.preheater_duty_pct  if data else None,
            "hours_total":        data.hours_total         if data else None,
            "rh_percent":         data.rh_percent          if data else None,
            "voc_ppm":            data.voc_ppm             if data else None,
            "co2_ppm":            data.co2_ppm             if data else None,
        }
        base["derived_state"] = {
            "heat_recovery_efficiency": data.heat_recovery_efficiency if data else None,
            "bypass_leaking":           data.bypass_leaking           if data else None,
            "motor_asymmetry":          data.motor_asymmetry          if data else None,
            "bypass_recommended":       data.bypass_recommended       if data else None,
            "frost_risk":               data.frost_risk               if data else None,
        }
        # Vollständiger Register-Dump für Reverse-Engineering / Debugging.
        # Block-weise und fehlertolerant; ein Fehler hier darf die restliche
        # Diagnose nicht verhindern.
        try:
            base["register_dump"] = await coordinator.async_dump_all_registers()
        except Exception as err:  # noqa: BLE001
            base["register_dump"] = {"error": repr(err)}
    else:
        # ── Touch Diagnose ────────────────────────────────────────────────────
        caps = coordinator.capabilities
        base["capabilities"] = (
            {
                "available_tags":       sorted(caps.available_tags),
                "unknown_tags":         sorted(caps.unknown_tags),
                "reachable_endpoints":  sorted(caps.reachable_endpoints),
                "has_motor_sensors":    caps.has_motor_sensors,
                "has_airflow_voltage":  caps.has_airflow_voltage,
                "has_temp_corrections": caps.has_temp_corrections,
                "has_ext_sensors":      caps.has_ext_sensors,
                "has_filter_lifetime":  caps.has_filter_lifetime,
                "has_operating_hours":  caps.has_operating_hours,
                "has_safety_manager":   caps.has_safety_manager,
                "has_installer_access": caps.has_installer_access,
                "has_time_sync":        caps.has_time_sync,
                "has_program_control":  caps.has_program_control,
                "summary":              caps.summary(),
            }
            if caps else "not_yet_discovered"
        )
        base["device_data"] = {
            "current_level":      data.current_level      if data else None,
            "current_level_text": data.current_level_text if data else None,
            "temp_abluft":        data.temp_abluft        if data else None,
            "temp_zuluft":        data.temp_zuluft        if data else None,
            "temp_aussenluft":    data.temp_aussenluft    if data else None,
            "temp_fortluft":      data.temp_fortluft      if data else None,
            "motor_zuluft_rpm":   data.motor_zuluft_rpm   if data else None,
            "motor_abluft_rpm":   data.motor_abluft_rpm   if data else None,
            "bypass_status":      data.bypass_status      if data else None,
            "filter_ok":          data.filter_ok          if data else None,
            "safety_active":      data.safety_active      if data else None,
            "control_mode":       data.control_mode       if data else None,
            "system_message":     data.system_message     if data else None,
            "hours_level_1":      data.hours_level_1      if data else None,
            "hours_level_2":      data.hours_level_2      if data else None,
            "hours_level_3":      data.hours_level_3      if data else None,
            "hours_level_4":      data.hours_level_4      if data else None,
        }
        base["derived_state"] = {
            "heat_recovery_efficiency": data.heat_recovery_efficiency if data else None,
            "heat_recovery_watts":      data.heat_recovery_watts      if data else None,
            "bypass_leaking":           data.bypass_leaking           if data else None,
            "motor_asymmetry":          data.motor_asymmetry          if data else None,
            "bypass_recommended":       data.bypass_recommended       if data else None,
            "frost_risk":               data.frost_risk               if data else None,
        }

    return base


def _lite_diagnostics(
    entry: KWLConfigEntry, coordinator: Any, config_data: dict[str, Any]
) -> dict[str, Any]:
    """Diagnose für lite-Geräte (REST).

    Enthält das ROHE ``RESULT``-Objekt der Statusantwort: Das ist der wichtigste
    Beitrag für die Hardware-Validierung, weil die Integration aus der App
    abgeleitet wurde (siehe docs/lite-rest.md) und Feldnamen/Skalierungen
    dadurch geprüft werden können.
    """
    data = coordinator.data
    return {
        "config_entry": config_data,
        "protocol": PROTOCOL_REST,
        "experimental": True,
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval else None
            ),
        },
        "options": {"scan_interval": entry.options.get("scan_interval", 30)},
        "device_data": (
            {
                "device_type": data.device_type,
                "firmware": data.firmware,
                "powered": data.powered,
                "function": data.function,
                "season": data.season,
                "room_temp": data.room_temp,
                "water_temp": data.water_temp,
                "setpoint": data.setpoint,
                "humidity": data.humidity,
                "air_quality_raw": data.air_quality_raw,
                "air_quality_level": data.air_quality_level,
                "alarms": list(data.alarms),
                "contact_presence": data.contact_presence,
                "key_lock": data.key_lock,
                "calendar_active": data.calendar_active,
                "standalone": data.standalone,
                "raw_result": data.result,
            }
            if data else None
        ),
    }

