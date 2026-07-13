"""Tests fuer select.py -- Bypass-Parsing und Option-Mappings."""
from __future__ import annotations

import pytest
import sys, os
from dataclasses import dataclass, field
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'custom_components'))

from kwl_fraenkische.select import (
    _parse_bypass,
    BYPASS_OPTIONS,
    BYPASS_STATUS_MAP,
)


class TestParseBypass:
    """Tests fuer _parse_bypass -- Freitext -> HA-Option Konvertierung."""

    def test_auto_offen(self):
        assert _parse_bypass("Auto: Offen") == "automatic"

    def test_auto_zu(self):
        assert _parse_bypass("Auto: Zu") == "automatic"

    def test_manuell_offen(self):
        assert _parse_bypass("Man.: Offen") == "manual_open"

    def test_manuell_zu(self):
        assert _parse_bypass("Man.: Zu") == "manual_closed"

    def test_case_insensitive(self):
        assert _parse_bypass("AUTO: OFFEN") == "automatic"

    def test_with_whitespace(self):
        assert _parse_bypass("  Auto: Offen  ") == "automatic"

    def test_unknown_returns_none(self):
        assert _parse_bypass("unbekannt") is None

    def test_empty_returns_none(self):
        assert _parse_bypass("") is None


class TestBypassOptions:
    """Tests fuer BYPASS_OPTIONS Mapping."""

    def test_all_three_options_present(self):
        assert "manual_open" in BYPASS_OPTIONS
        assert "manual_closed" in BYPASS_OPTIONS
        assert "automatic" in BYPASS_OPTIONS

    def test_post_values_correct(self):
        assert BYPASS_OPTIONS["manual_open"] == "bypa0"
        assert BYPASS_OPTIONS["manual_closed"] == "bypa1"
        assert BYPASS_OPTIONS["automatic"] == "bypa2"

    def test_all_post_values_unique(self):
        values = list(BYPASS_OPTIONS.values())
        assert len(values) == len(set(values))


class TestSensorTypeNormalization:
    """Tests fuer _normalize_sensor_type."""

    def test_nicht_aktiv(self):
        from kwl_fraenkische.select import _normalize_sensor_type
        assert _normalize_sensor_type("Nicht aktiv") == "Keiner"

    def test_feuchte(self):
        from kwl_fraenkische.select import _normalize_sensor_type
        assert _normalize_sensor_type("%H") == "Feuchte (%H)"

    def test_co2_ppm(self):
        from kwl_fraenkische.select import _normalize_sensor_type
        assert _normalize_sensor_type("ppm") == "CO2 (ppm)"

    def test_empty_string(self):
        from kwl_fraenkische.select import _normalize_sensor_type
        assert _normalize_sensor_type("") == "Keiner"

    def test_unknown_fallback(self):
        from kwl_fraenkische.select import _normalize_sensor_type
        assert _normalize_sensor_type("irgendwas") == "Keiner"


class TestInstallTypeNormalization:
    """Tests fuer _normalize_install_type."""

    def test_eigenheim(self):
        from kwl_fraenkische.select import _normalize_install_type
        assert _normalize_install_type("Eigenheim") == "single_family"

    def test_mietwohnung(self):
        from kwl_fraenkische.select import _normalize_install_type
        assert _normalize_install_type("Mietwohnung") == "apartment"

    def test_case_insensitive(self):
        from kwl_fraenkische.select import _normalize_install_type
        assert _normalize_install_type("EIGENHEIM") == "single_family"

    def test_unknown_returns_none(self):
        from kwl_fraenkische.select import _normalize_install_type
        assert _normalize_install_type("unbekannt") is None
