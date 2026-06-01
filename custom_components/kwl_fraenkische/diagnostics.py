"""Diagnostics fuer die KWL Fraenkische Rohrwerke Integration."""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import KWLConfigEntry

REDACTED = "**REDACTED**"


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: KWLConfigEntry,
) -> dict[str, Any]:
    """Diagnosedaten fuer den Download-Diagnose-Dialog in HA.

    Sensitive Daten (Passwort, MAC) werden automatisch geschwärzt.
    """
    coordinator = entry.runtime_data

    config_data = dict(entry.data)
    config_data["password"] = REDACTED
    if "mac" in config_data:
        config_data["mac"] = REDACTED

    data = coordinator.data

    return {
        "config_entry": config_data,
        "capabilities": (
            {
                "available_tags": sorted(coordinator.capabilities.available_tags),
                "unknown_tags": sorted(coordinator.capabilities.unknown_tags),
                "reachable_endpoints": sorted(coordinator.capabilities.reachable_endpoints),
                "has_motor_sensors": coordinator.capabilities.has_motor_sensors,
                "has_airflow_voltage": coordinator.capabilities.has_airflow_voltage,
                "has_temp_corrections": coordinator.capabilities.has_temp_corrections,
                "has_ext_sensors": coordinator.capabilities.has_ext_sensors,
                "has_filter_lifetime": coordinator.capabilities.has_filter_lifetime,
                "has_operating_hours": coordinator.capabilities.has_operating_hours,
                "has_safety_manager": coordinator.capabilities.has_safety_manager,
                "has_installer_access": coordinator.capabilities.has_installer_access,
                "has_time_sync": coordinator.capabilities.has_time_sync,
                "has_program_control": coordinator.capabilities.has_program_control,
                "summary": coordinator.capabilities.summary(),
            }
            if coordinator.capabilities else "not_yet_discovered"
        ),
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval_seconds": coordinator.update_interval.total_seconds()
            if coordinator.update_interval
            else None,
        },
        "options": {
            "scan_interval": entry.options.get("scan_interval", 30),
            "watt_map": coordinator.watt_map,
        },
        "derived_state": {
            "heat_recovery_efficiency": coordinator.data.heat_recovery_efficiency
            if coordinator.data else None,
            "heat_recovery_watts": coordinator.data.heat_recovery_watts
            if coordinator.data else None,
            "bypass_leaking": coordinator.data.bypass_leaking
            if coordinator.data else None,
            "motor_asymmetry": coordinator.data.motor_asymmetry
            if coordinator.data else None,
            "bypass_recommended": coordinator.data.bypass_recommended
            if coordinator.data else None,
            "frost_risk": coordinator.data.frost_risk
            if coordinator.data else None,
        },
        "capabilities": {
            "available_tags": sorted(coordinator.capabilities.available_tags)
            if coordinator.capabilities else None,
            "reachable_endpoints": sorted(coordinator.capabilities.reachable_endpoints)
            if coordinator.capabilities else None,
            "unknown_tags": sorted(coordinator.capabilities.unknown_tags)
            if coordinator.capabilities else None,
            "has_motor_sensors": coordinator.capabilities.has_motor_sensors
            if coordinator.capabilities else None,
            "has_installer_access": coordinator.capabilities.has_installer_access
            if coordinator.capabilities else None,
            "has_time_sync": coordinator.capabilities.has_time_sync
            if coordinator.capabilities else None,
            "has_program_control": coordinator.capabilities.has_program_control
            if coordinator.capabilities else None,
            "has_ext_sensors": coordinator.capabilities.has_ext_sensors
            if coordinator.capabilities else None,
            "has_filter_lifetime": coordinator.capabilities.has_filter_lifetime
            if coordinator.capabilities else None,
            "has_airflow_voltage": coordinator.capabilities.has_airflow_voltage
            if coordinator.capabilities else None,
            "has_temp_corrections": coordinator.capabilities.has_temp_corrections
            if coordinator.capabilities else None,
        },
        "device_data": {
            "current_level": data.current_level if data else None,
            "current_level_text": data.current_level_text if data else None,
            "temp_abluft": data.temp_abluft if data else None,
            "temp_zuluft": data.temp_zuluft if data else None,
            "temp_aussenluft": data.temp_aussenluft if data else None,
            "temp_fortluft": data.temp_fortluft if data else None,
            "motor_zuluft_rpm": data.motor_zuluft_rpm if data else None,
            "motor_abluft_rpm": data.motor_abluft_rpm if data else None,
            "bypass_status": data.bypass_status if data else None,
            "filter_ok": data.filter_ok if data else None,
            "safety_active": data.safety_active if data else None,
            "control_mode": data.control_mode if data else None,
            "system_message": data.system_message if data else None,
            "hours_level_1": data.hours_level_1 if data else None,
            "hours_level_2": data.hours_level_2 if data else None,
            "hours_level_3": data.hours_level_3 if data else None,
            "hours_level_4": data.hours_level_4 if data else None,
        },
    }
