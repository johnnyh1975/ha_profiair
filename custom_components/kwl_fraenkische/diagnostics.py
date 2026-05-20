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
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval_seconds": coordinator.update_interval.total_seconds()
            if coordinator.update_interval
            else None,
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
