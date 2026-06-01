"""Tests fuer sensor.py -- Energie-Berechnung und Sensor-Werte."""
from __future__ import annotations

import pytest
import sys, os
from dataclasses import dataclass, field
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'custom_components'))

from kwl_fraenkische.sensor import _energy_kwh
from kwl_fraenkische.const import LEVEL_TO_WATT


class TestEnergyCalculation:
    def test_zero_hours(self):
        assert _energy_kwh(0, 11.0) == 0.0

    def test_none_hours_returns_none(self):
        assert _energy_kwh(None, 11.0) is None

    def test_level1_calculation(self):
        result = _energy_kwh(133582, 11.0)
        assert result == round(133582 * 11.0 / 1000, 2)

    def test_level2_calculation(self):
        result = _energy_kwh(16324, 17.5)
        assert result == round(16324 * 17.5 / 1000, 2)

    def test_result_rounded_to_2_decimals(self):
        assert _energy_kwh(1, 11.0) == 0.01

    def test_monoton_steigend(self):
        assert _energy_kwh(101, 11.0) > _energy_kwh(100, 11.0)


class TestSensorDescriptions:
    def test_all_temperature_sensors_present(self):
        from kwl_fraenkische.sensor import SENSORS
        keys = {s.key for s in SENSORS}
        for k in ["temp_abluft", "temp_zuluft", "temp_aussenluft", "temp_fortluft"]:
            assert k in keys

    def test_temperature_sensors_have_force_update(self):
        from kwl_fraenkische.sensor import SENSORS
        for s in SENSORS:
            if s.key.startswith("temp_"):
                assert s.force_update is True

    def test_energy_sensors_present(self):
        from kwl_fraenkische.sensor import SENSORS
        keys = {s.key for s in SENSORS}
        for i in range(1, 5):
            assert f"energy_level_{i}" in keys

    def test_betriebsstunden_disabled_by_default(self):
        from kwl_fraenkische.sensor import SENSORS
        for s in SENSORS:
            if s.key.startswith("hours_level_"):
                assert s.entity_registry_enabled_default is False


    def test_value_functions_dont_crash(self, sample_xml):
        from kwl_fraenkische.sensor import SENSORS
        from kwl_fraenkische.coordinator import KWLData, _parse_xml
        data = KWLData(_parse_xml(sample_xml))
        for sensor in SENSORS:
            try:
                sensor.value_fn(data)
            except Exception as e:
                pytest.fail(f"Sensor {sensor.key} value_fn crashed: {e}")


class TestNewSensorDescriptions:
    """Tests fuer neue Sensoren aus v1.3+."""

    def test_heat_recovery_sensors_present(self):
        """Waermerueckgewinnung Sensoren sind definiert."""
        from kwl_fraenkische.sensor import SENSORS
        keys = {d.key for d in SENSORS}
        assert "heat_recovery_efficiency" in keys
        assert "heat_recovery_watts" in keys

    def test_heat_recovery_efficiency_has_force_update(self):
        """eta Sensor hat force_update=True fuer lueckenlose Aufzeichnung."""
        from kwl_fraenkische.sensor import SENSORS
        desc = next(d for d in SENSORS if d.key == "heat_recovery_efficiency")
        assert desc.force_update is True

    def test_heat_recovery_watts_has_power_device_class(self):
        from kwl_fraenkische.sensor import SENSORS
        from homeassistant.components.sensor import SensorDeviceClass
        desc = next(d for d in SENSORS if d.key == "heat_recovery_watts")
        assert desc.device_class == SensorDeviceClass.POWER

    def test_filter_sensors_have_required_tag(self):
        """Filter-Sensoren nur wenn Tag vorhanden."""
        from kwl_fraenkische.sensor import SENSORS
        for key in ("filter_total_days", "filter_residual_days"):
            desc = next(d for d in SENSORS if d.key == key)
            assert desc.required_tag is not None

    def test_all_hours_sensors_have_required_tag(self):
        """Alle Betriebsstunden-Sensoren haben required_tag."""
        from kwl_fraenkische.sensor import SENSORS
        for i in range(1, 5):
            desc = next(d for d in SENSORS if d.key == f"hours_level_{i}")
            assert desc.required_tag == f"BsSt{i}", \
                f"hours_level_{i} hat falschen required_tag: {desc.required_tag}"

    def test_watt_sensor_keys(self):
        """_WATT_SENSOR_KEYS enthaelt alle watt-abhaengigen Sensoren."""
        from kwl_fraenkische.sensor import _WATT_SENSOR_KEYS
        assert "power_current" in _WATT_SENSOR_KEYS
        for i in range(1, 5):
            assert f"energy_level_{i}" in _WATT_SENSOR_KEYS

    def test_diagnostic_sensors_have_entity_category(self):
        """Diagnose-Sensoren haben entity_category=DIAGNOSTIC."""
        from kwl_fraenkische.sensor import SENSORS
        from homeassistant.helpers.entity import EntityCategory
        diagnostic_keys = {
            "motor_zuluft_rpm", "motor_abluft_rpm",
            "motor_zuluft_volt", "motor_abluft_volt",
            "hours_level_1", "hours_level_2", "hours_level_3", "hours_level_4",
            "hours_frost", "hours_preheater",
            "filter_total_days", "filter_residual_days",
            "system_message",
        }
        for desc in SENSORS:
            if desc.key in diagnostic_keys:
                assert desc.entity_category is not None, \
                    f"{desc.key} hat kein entity_category"
