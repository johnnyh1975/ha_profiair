"""Tests fuer fan.py -- Stufen-Mapping und Prozent-Logik."""
from __future__ import annotations

import pytest
import sys, os
from dataclasses import dataclass, field
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'custom_components'))

from kwl_fraenkische.fan import (
    PRESET_MODES,
    LEVEL_TO_PRESET,
    LEVEL_TO_PERCENT,
    _percent_to_level,
)


class TestPercentToLevel:
    """Tests fuer die Prozent -> Stufe Konvertierung."""

    def test_0_percent_gives_level_1(self):
        assert _percent_to_level(0) == 1

    def test_25_percent_gives_level_1(self):
        assert _percent_to_level(25) == 1

    def test_30_percent_gives_level_1(self):
        """Grenzwert: 30% ist noch Stufe 1."""
        assert _percent_to_level(30) == 1

    def test_31_percent_gives_level_2(self):
        """Grenzwert: 31% ist bereits Stufe 2."""
        assert _percent_to_level(31) == 2

    def test_50_percent_gives_level_2(self):
        assert _percent_to_level(50) == 2

    def test_55_percent_gives_level_2(self):
        """Grenzwert: 55% ist noch Stufe 2."""
        assert _percent_to_level(55) == 2

    def test_56_percent_gives_level_3(self):
        """Grenzwert: 56% ist bereits Stufe 3."""
        assert _percent_to_level(56) == 3

    def test_75_percent_gives_level_3(self):
        assert _percent_to_level(75) == 3

    def test_80_percent_gives_level_3(self):
        """Grenzwert: 80% ist noch Stufe 3."""
        assert _percent_to_level(80) == 3

    def test_81_percent_gives_level_4(self):
        """Grenzwert: 81% ist bereits Stufe 4."""
        assert _percent_to_level(81) == 4

    def test_100_percent_gives_level_4(self):
        assert _percent_to_level(100) == 4


class TestLevelToPercent:
    """Tests fuer Level -> Prozent Mapping."""

    def test_level_1_is_25_percent(self):
        assert LEVEL_TO_PERCENT[1] == 25

    def test_level_2_is_50_percent(self):
        assert LEVEL_TO_PERCENT[2] == 50

    def test_level_3_is_75_percent(self):
        assert LEVEL_TO_PERCENT[3] == 75

    def test_level_4_is_100_percent(self):
        assert LEVEL_TO_PERCENT[4] == 100

    def test_all_levels_covered(self):
        assert set(LEVEL_TO_PERCENT.keys()) == {1, 2, 3, 4}


class TestPresetModes:
    """Tests fuer Preset-Mode Mappings."""

    def test_all_presets_have_level(self):
        for preset, level in PRESET_MODES.items():
            assert level in (1, 2, 3, 4), f"Preset '{preset}' hat ungueltige Stufe {level}"

    def test_level_to_preset_reverse_mapping(self):
        """LEVEL_TO_PRESET muss die Umkehrung von PRESET_MODES sein."""
        for preset, level in PRESET_MODES.items():
            assert LEVEL_TO_PRESET[level] == preset

    def test_4_presets_defined(self):
        assert len(PRESET_MODES) == 4

    def test_stufe1_preset_name(self):
        assert PRESET_MODES.get("Stufe 1 - Feuchteschutz") == 1

    def test_stufe4_preset_name(self):
        assert PRESET_MODES.get("Stufe 4 - Intensivlueftung") == 4


class TestWattMapping:
    """Tests fuer Watt-Werte pro Stufe."""

    def test_watt_values_imported_from_const(self):
        from kwl_fraenkische.const import LEVEL_TO_WATT
        assert LEVEL_TO_WATT[1] == 11.0
        assert LEVEL_TO_WATT[2] == 17.5
        assert LEVEL_TO_WATT[3] == 43.5
        assert LEVEL_TO_WATT[4] == 80.0

    def test_watt_increases_with_level(self):
        from kwl_fraenkische.const import LEVEL_TO_WATT
        assert LEVEL_TO_WATT[1] < LEVEL_TO_WATT[2] < LEVEL_TO_WATT[3] < LEVEL_TO_WATT[4]

    def test_all_levels_have_watt(self):
        from kwl_fraenkische.const import LEVEL_TO_WATT
        assert set(LEVEL_TO_WATT.keys()) == {1, 2, 3, 4}
