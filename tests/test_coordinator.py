"""Tests fuer coordinator.py -- KWLData Parsing und Normalisierung."""
from __future__ import annotations

import pytest
from xml.etree import ElementTree

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'custom_components'))

from kwl_fraenkische.coordinator import (
    KWLData,
    _parse_float,
    _parse_int,
    _parse_volt,
    _parse_korrektur,
    _parse_xml,
    _build_time_payload,
    _build_dst_payload,
)


# ── XML Parsing ────────────────────────────────────────────────────────────

class TestParseXml:
    def test_parses_flat_xml(self, sample_xml):
        result = _parse_xml(sample_xml)
        assert isinstance(result, dict)
        assert "abl0" in result
        assert "stufe1" in result

    def test_strips_whitespace_in_values(self, sample_xml):
        # abl0 hat fuehrende Leerzeichen: " 22.1"
        result = _parse_xml(sample_xml)
        # Rohwert behaelt Whitespace -- _parse_float entfernt ihn
        assert result["abl0"].strip() == "22.1"

    def test_empty_tags_return_empty_string(self):
        xml = "<response><empty></empty></response>"
        result = _parse_xml(xml)
        assert result["empty"] == ""

    def test_invalid_xml_raises(self):
        with pytest.raises(ElementTree.ParseError):
            _parse_xml("kein xml")

    def test_mac_address_parsed(self, sample_xml):
        result = _parse_xml(sample_xml)
        assert result["config_mac"].strip() == "00:04:A3:76:23:66"


# ── Helper-Funktionen ──────────────────────────────────────────────────────

class TestParseHelpers:
    def test_parse_float_valid(self):
        assert _parse_float(" 22.1") == 22.1

    def test_parse_float_none(self):
        assert _parse_float(None) is None

    def test_parse_float_invalid(self):
        assert _parse_float("nicht_eine_zahl") is None

    def test_parse_int_valid(self):
        assert _parse_int("1022") == 1022

    def test_parse_int_none(self):
        assert _parse_int(None) is None

    def test_parse_int_whitespace(self):
        assert _parse_int(" 42 ") == 42

    def test_parse_volt_divides_by_10(self):
        assert _parse_volt("24") == 2.4

    def test_parse_volt_none(self):
        assert _parse_volt(None) is None

    def test_parse_volt_zero(self):
        assert _parse_volt("0") == 0.0

    def test_parse_korrektur_divides_by_10(self):
        assert _parse_korrektur("5") == 0.5

    def test_parse_korrektur_zero(self):
        assert _parse_korrektur("00") == 0.0

    def test_parse_korrektur_negative(self):
        assert _parse_korrektur("-5") == -0.5


# ── KWLData Properties ────────────────────────────────────────────────────

class TestKWLData:

    @pytest.fixture
    def data(self, sample_xml):
        raw = _parse_xml(sample_xml)
        return KWLData(raw)

    # Lueeftungsstufen
    def test_current_level_stufe1(self, data):
        assert data.current_level == 1

    def test_current_level_fallback(self):
        """Wenn kein Flag gesetzt ist, Fallback auf 1."""
        d = KWLData({"stufe1": "0", "stufe2": "0", "stufe3": "0", "stufe4": "0"})
        assert d.current_level == 1

    def test_current_level_stufe3(self):
        d = KWLData({"stufe1": "0", "stufe2": "0", "stufe3": "1", "stufe4": "0"})
        assert d.current_level == 3

    def test_current_level_text(self, data):
        assert data.current_level_text == "Stufe1 Feuchteschutz"

    # Temperaturen
    def test_temp_abluft(self, data):
        assert data.temp_abluft == 22.1

    def test_temp_zuluft(self, data):
        assert data.temp_zuluft == 19.9

    def test_temp_aussenluft(self, data):
        assert data.temp_aussenluft == 18.8

    def test_temp_fortluft(self, data):
        assert data.temp_fortluft == 20.4

    # Volt-Skalierung (/ 10)
    def test_motor_zuluft_volt_scaled(self, data):
        """MoStZlVo=24 muss als 2.4V ausgegeben werden."""
        assert data.motor_zuluft_volt == 2.4

    def test_motor_abluft_volt_scaled(self, data):
        assert data.motor_abluft_volt == 2.1

    def test_airflow_s1_supply_scaled(self, data):
        """st1z=24 muss als 2.4V ausgegeben werden."""
        assert data.airflow_s1_supply == 2.4

    def test_airflow_s4_exhaust_scaled(self, data):
        """st4a=65 muss als 6.5V ausgegeben werden."""
        assert data.airflow_s4_exhaust == 6.5

    # Korrekturen (/ 10)
    def test_korrektur_abluft_zero(self, data):
        """kor1=' 00' muss als 0.0 ausgegeben werden."""
        assert data.korrektur_abluft == 0.0

    # Motorstatus
    def test_motor_zuluft_rpm(self, data):
        assert data.motor_zuluft_rpm == 1022

    def test_motor_abluft_rpm(self, data):
        assert data.motor_abluft_rpm == 854

    # Betriebsstunden
    def test_hours_level_1(self, data):
        assert data.hours_level_1 == 133582

    def test_hours_level_4(self, data):
        assert data.hours_level_4 == 75

    # Status-Properties
    def test_filter_ok_when_replaced(self, data):
        """'Filter ersetzt' bedeutet Filter OK."""
        assert data.filter_ok is True

    def test_filter_not_ok(self):
        d = KWLData({"filter0": "Filter wechseln"})
        assert d.filter_ok is False

    def test_safety_not_active(self, data):
        assert data.safety_active is False

    def test_safety_active(self):
        d = KWLData({"safety": "Aktiv"})
        assert d.safety_active is True

    def test_passive_mode_off(self, data):
        assert data.passive_mode is False

    def test_passive_mode_on(self):
        d = KWLData({"passiv": "Ein"})
        assert d.passive_mode is True

    def test_preheater_not_active(self, data):
        assert data.preheater_active is False

    def test_preheater_active(self):
        d = KWLData({"vorheiz": "Aktiv"})
        assert d.preheater_active is True

    def test_bypass_status(self, data):
        assert data.bypass_status == "Auto: Offen"

    def test_control_mode(self, data):
        assert data.control_mode == "manuelle Stufenwahl"

    def test_party_timer(self, data):
        assert data.party_timer_minutes == 120

    def test_bypass_threshold_aul(self, data):
        assert data.bypass_threshold_aul == 15.0

    def test_bypass_threshold_abl(self, data):
        assert data.bypass_threshold_abl == 22.0

    def test_install_type(self, data):
        assert data.install_type == "Eigenheim"

    def test_ext_sensor_type_1_not_active(self, data):
        assert "Nicht aktiv" in data.ext_sensor_type_1

    def test_raw_access(self, data):
        assert data.raw("config_ip") is not None


# ── Zeitsynchronisation ────────────────────────────────────────────────────

class TestTimeSyncPayload:
    def test_time_payload_format(self):
        from datetime import datetime, timezone, timedelta
        # Mittwoch 15.04.2026 14:30:45 CEST (+2h)
        tz = timezone(timedelta(hours=2))
        now = datetime(2026, 4, 15, 14, 30, 45, tzinfo=tz)
        payload = _build_time_payload(now)
        assert "timesubmit" in payload
        ts = payload["timesubmit"]
        assert ts.startswith("J26")   # Jahr 2026 -> 26
        assert "M04" in ts            # April
        assert "T15" in ts            # Tag 15
        assert "h14" in ts            # Stunde 14
        assert "m30" in ts            # Minute 30
        assert "s45" in ts            # Sekunde 45

    def test_dst_payload_summer(self):
        from datetime import datetime, timezone, timedelta
        tz = timezone(timedelta(hours=2))
        # Sommerzeit simulieren: dst() > 0
        import pytz
        try:
            berlin = pytz.timezone("Europe/Berlin")
            summer = berlin.localize(datetime(2026, 7, 15, 12, 0, 0))
            payload = _build_dst_payload(summer)
            assert payload["SoZeit"] == "soze1"
        except ImportError:
            pytest.skip("pytz nicht installiert")

    def test_dst_payload_winter(self):
        from datetime import datetime
        import pytz
        try:
            berlin = pytz.timezone("Europe/Berlin")
            winter = berlin.localize(datetime(2026, 1, 15, 12, 0, 0))
            payload = _build_dst_payload(winter)
            assert payload["SoZeit"] == "soze0"
        except ImportError:
            pytest.skip("pytz nicht installiert")
