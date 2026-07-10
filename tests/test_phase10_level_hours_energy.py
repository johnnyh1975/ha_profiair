"""Tests für selbst gezählte Stufen-Betriebsstunden und geschätzte
flex/flat-Energiesensoren (2.0.7).

flex/flat liefern keine Betriebsstunden pro Stufe über Modbus. Der
LevelHoursTracker zählt die Zeit je Stufe poll-basiert selbst; daraus werden
geschätzte Energiewerte (Stunden × Watt) berechnet.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(
    0, str(Path(__file__).parent.parent / "custom_components" / "kwl_fraenkische")
)

from analytics import LevelHoursTracker  # noqa: E402


class TestLevelHoursTracker:
    def test_accumulates_per_level(self):
        t = LevelHoursTracker()
        # 3600 s auf Stufe 2 = 1.0 h
        for _ in range(120):
            t.update(2, 30.0)
        assert t.hours(2) == pytest.approx(1.0, abs=0.001)
        assert t.hours(1) == 0.0
        assert t.hours(3) == 0.0

    def test_ignores_invalid_level(self):
        t = LevelHoursTracker()
        t.update(None, 30.0)
        t.update(0, 30.0)
        t.update(5, 30.0)
        for lvl in (1, 2, 3, 4):
            assert t.hours(lvl) == 0.0

    def test_ignores_nonpositive_interval(self):
        t = LevelHoursTracker()
        t.update(1, 0.0)
        t.update(1, -30.0)
        assert t.hours(1) == 0.0

    def test_invalid_level_query_returns_none(self):
        t = LevelHoursTracker()
        assert t.hours(0) is None
        assert t.hours(9) is None

    def test_persistence_roundtrip(self):
        t = LevelHoursTracker()
        for _ in range(10):
            t.update(3, 30.0)   # 300 s
        for _ in range(5):
            t.update(4, 30.0)   # 150 s
        d = t.to_dict()
        t2 = LevelHoursTracker.from_dict(d)
        assert t2.hours(3) == pytest.approx(300 / 3600, abs=0.001)
        assert t2.hours(4) == pytest.approx(150 / 3600, abs=0.001)

    def test_from_dict_none_is_fresh(self):
        t = LevelHoursTracker.from_dict(None)
        for lvl in (1, 2, 3, 4):
            assert t.hours(lvl) == 0.0

    def test_monotonic_never_decreases(self):
        """Für TOTAL_INCREASING: der Zähler darf nie fallen."""
        t = LevelHoursTracker()
        last = 0.0
        for _ in range(50):
            t.update(1, 30.0)
            now = t.hours(1)
            assert now >= last
            last = now


class TestLevelHoursInAnalytics:
    """LevelHoursTracker muss in KWLAnalytics integriert und persistiert sein."""

    def _analytics_src(self) -> str:
        return open(
            Path(__file__).parent.parent
            / "custom_components" / "kwl_fraenkische" / "analytics.py"
        ).read()

    def test_analytics_persists_level_hours(self):
        src = self._analytics_src()
        assert '"level_hours"' in src
        assert "self._level_hours.to_dict()" in src
        assert "LevelHoursTracker.from_dict" in src

    def test_analytics_updates_level_hours_each_poll(self):
        src = self._analytics_src()
        assert "self._level_hours.update(snap.current_level, poll_interval_s)" in src

    def test_analytics_exposes_level_hours_accessor(self):
        src = self._analytics_src()
        assert "def level_hours(self, level: int)" in src


class TestFlexEnergyEstimation:
    """Die geschätzten flex-Energiesensoren müssen aus Stunden × Watt rechnen."""

    def _flex_src(self) -> str:
        return open(
            Path(__file__).parent.parent
            / "custom_components" / "kwl_fraenkische" / "flex_coordinator.py"
        ).read()

    def _sensor_src(self) -> str:
        return open(
            Path(__file__).parent.parent
            / "custom_components" / "kwl_fraenkische" / "sensor.py"
        ).read()

    def test_flex_data_computes_energy(self):
        src = self._flex_src()
        assert "_energy_level_kwh" in src
        assert "def energy_total" in src
        # Formel: hours * watt / 1000
        assert "hours * watt / 1000.0" in src

    def test_flex_energy_sensors_are_modbus_only(self):
        src = self._sensor_src()
        for key in (
            "energy_level_1_flex", "energy_level_2_flex", "energy_level_3_flex",
            "energy_level_4_flex", "energy_total_flex",
        ):
            idx = src.find(f'key="{key}"')
            assert idx >= 0, f"{key} fehlt"
            block = src[idx:idx + 500]
            assert "PROTOCOL_MODBUS" in block, f"{key} muss Modbus-only sein"
            assert "TOTAL_INCREASING" in block

    def test_flex_energy_sensors_marked_estimated(self):
        """Die Namen müssen '(geschätzt)' tragen, damit niemand sie mit einer
        echten Messung verwechselt."""
        src = self._sensor_src()
        for key in ("energy_level_1_flex", "energy_total_flex"):
            idx = src.find(f'key="{key}"')
            block = src[idx:idx + 500]
            assert "geschätzt" in block

    def test_energy_total_tolerates_missing_levels(self):
        src = self._flex_src()
        idx = src.find("def energy_total")
        block = src[idx:idx + 400]
        # Summe der vorhandenen, None wenn keine
        assert "valid" in block
        assert "None" in block
