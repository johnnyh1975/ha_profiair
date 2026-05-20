"""Tests fuer sensor.py -- Energie-Berechnung und Sensor-Werte."""
from __future__ import annotations

import pytest
import sys, os
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

    def test_frost_preheater_present(self):
        from kwl_fraenkische.sensor import SENSORS
        keys = {s.key for s in SENSORS}
        assert "hours_frost" in keys
        assert "hours_preheater" in keys

    def test_value_functions_dont_crash(self, sample_xml):
        from kwl_fraenkische.sensor import SENSORS
        from kwl_fraenkische.coordinator import KWLData, _parse_xml
        data = KWLData(_parse_xml(sample_xml))
        for sensor in SENSORS:
            try:
                sensor.value_fn(data)
            except Exception as e:
                pytest.fail(f"Sensor {sensor.key} value_fn crashed: {e}")
