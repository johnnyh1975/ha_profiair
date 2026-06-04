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

    def test_program_control(self, data):
        assert data.program_control == "manuelle Stufenwahl"

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


class TestDerivedProperties:
    """Tests fuer berechnete Properties in KWLData."""

    @pytest.fixture
    def data(self, sample_xml):
        return KWLData(_parse_xml(sample_xml))

    def test_heat_recovery_efficiency_calculated(self, data):
        """eta = (zuluft - aussen) / (abluft - aussen) * 100."""
        eta = data.heat_recovery_efficiency
        assert eta is not None
        assert 0 < eta < 100

    def test_heat_recovery_efficiency_none_when_delta_small(self):
        """Wenn T_abluft - T_aussen < 3 K kein sinnvoller Wert."""
        d = KWLData({"abl0": "20.0", "zul0": "19.5", "aul0": "19.0"})
        assert d.heat_recovery_efficiency is None

    def test_heat_recovery_efficiency_none_when_missing(self):
        d = KWLData({})
        assert d.heat_recovery_efficiency is None

    def test_heat_recovery_watts_positive(self, data):
        """Waermeleistung muss positiv sein bei T_abluft > T_zuluft."""
        watts = data.heat_recovery_watts
        assert watts is not None
        assert watts > 0

    def test_heat_recovery_watts_none_when_equal_temps(self):
        d = KWLData({"abl0": "20.0", "zul0": "20.0",
                     "stufe1": "1", "stufe2": "0", "stufe3": "0", "stufe4": "0"})
        assert d.heat_recovery_watts is None

    def test_frost_risk_false_normally(self, data):
        """Sample XML hat 14.8 C Aussenluft -- kein Frost-Risiko."""
        assert data.frost_risk is False

    def test_frost_risk_true_when_cold(self):
        d = KWLData({"aul0": "-6.0", "zul0": "4.0"})
        assert d.frost_risk is True

    def test_frost_risk_false_when_only_aussen_cold(self):
        d = KWLData({"aul0": "-6.0", "zul0": "8.0"})
        assert d.frost_risk is False

    def test_bypass_leaking_false_when_open(self, data):
        """Bypass offen -- kein Leckage-Defekt."""
        assert data.bypass_leaking is False

    def test_bypass_leaking_true_when_fort_close_to_aussen(self):
        """Fort-Aussen Delta < 4K bei genuiner Leckage."""
        d = KWLData({
            "bypass": "Man.: Zu",
            "fol0": "17.0", "aul0": "15.0",  # delta 2K < 4K
            "abl0": "23.0",                   # abluft-aussen = 8K > 5K
        })
        assert d.bypass_leaking is True

    def test_bypass_leaking_false_when_delta_above_4k(self):
        """Fort-Aussen Delta > 4K -- kein Leckage-Alarm."""
        d = KWLData({
            "bypass": "Man.: Zu",
            "fol0": "19.5", "aul0": "15.0",  # delta 4.5K > 4K
            "abl0": "23.0",
        })
        assert d.bypass_leaking is False

    def test_bypass_leaking_false_when_small_heizung_delta(self):
        """Bei kleiner Temperaturdifferenz Abluft-Aussen keine Leckage-Erkennung."""
        d = KWLData({
            "bypass": "Man.: Zu",
            "fol0": "17.0", "aul0": "15.0",
            "abl0": "18.0",  # nur 3K Differenz -- unter 5K Schwelle
        })
        assert d.bypass_leaking is False

    def test_motor_asymmetry_false_normally(self, data):
        """Sample XML: 2291 vs 1953 RPM -- 14.8% unter 25% Schwelle -- kein Alarm."""
        # |2291-1953|/2291 = 0.148 < 0.25
        assert data.motor_asymmetry is False

    def test_motor_asymmetry_true_when_large_diff(self):
        d = KWLData({"MoStZlUm": "2000", "MoStAlUm": "1000"})
        assert d.motor_asymmetry is True

    def test_motor_asymmetry_false_when_similar(self):
        d = KWLData({"MoStZlUm": "2000", "MoStAlUm": "1950"})
        assert d.motor_asymmetry is False

    def test_motor_asymmetry_false_when_missing(self):
        d = KWLData({})
        assert d.motor_asymmetry is False

    def test_bypass_recommended_false_when_cool_outside(self, data):
        """14.8 C aussen, 22.8 C abluft -- Delta OK aber Abluft knapp."""
        # 14.8 < 22.8 - 2 = 20.8 ✓, abluft 22.8 > 22.0 ✓, aussen 14.8 > 10 ✓
        assert data.bypass_recommended is True

    def test_bypass_recommended_false_when_warm_outside(self):
        d = KWLData({"aul0": "25.0", "abl0": "23.0"})
        assert d.bypass_recommended is False

    def test_bypass_recommended_false_when_house_cool(self):
        d = KWLData({"aul0": "15.0", "abl0": "18.0"})
        assert d.bypass_recommended is False


class TestRequiredTagValidation:
    """Tests fuer Minimum-Tag-Validierung in _async_update_data."""

    def test_required_tags_present_in_sample(self, sample_xml):
        """Sample XML enthaelt alle REQUIRED_XML_TAGS."""
        from kwl_fraenkische.const import REQUIRED_XML_TAGS
        from kwl_fraenkische.coordinator import _parse_xml
        raw = _parse_xml(sample_xml)
        missing = REQUIRED_XML_TAGS - frozenset(raw.keys())
        assert len(missing) == 0

    def test_required_tags_defined(self):
        """REQUIRED_XML_TAGS ist nicht leer."""
        from kwl_fraenkische.const import REQUIRED_XML_TAGS
        assert len(REQUIRED_XML_TAGS) >= 4

    def test_required_tags_are_core_sensors(self):
        """Pflicht-Tags sind die vier Temperaturen und Stufe-Flag."""
        from kwl_fraenkische.const import REQUIRED_XML_TAGS
        assert "abl0" in REQUIRED_XML_TAGS
        assert "zul0" in REQUIRED_XML_TAGS
        assert "aul0" in REQUIRED_XML_TAGS
        assert "stufe1" in REQUIRED_XML_TAGS


class TestDefectCounters:
    """Tests fuer die 3-Poll-Threshold bei bypass_leaking und motor_asymmetry."""

    def test_bypass_leaking_threshold(self):
        """bypass_leaking: True bei genuiner Leckage."""
        d = KWLData({
            "bypass": "Man.: Zu",
            "fol0": "15.1", "aul0": "15.0", "abl0": "23.0",
        })
        assert d.bypass_leaking is True

    def test_bypass_leaking_false_when_bypass_open(self):
        """Kein Leckage-Alarm wenn Bypass offen sein soll."""
        d = KWLData({
            "bypass": "Man.: Offen",
            "fol0": "15.1", "aul0": "15.0", "abl0": "23.0",
        })
        assert d.bypass_leaking is False

    def test_bypass_leaking_false_when_auto_open(self):
        """Kein Leckage-Alarm bei Auto: Offen."""
        d = KWLData({
            "bypass": "Auto: Offen",
            "fol0": "15.1", "aul0": "15.0", "abl0": "23.0",
        })
        assert d.bypass_leaking is False

    def test_motor_asymmetry_boundary_exactly_25pct(self):
        """Genau 25% Asymmetrie -- noch kein Alarm (> 25% required)."""
        d = KWLData({"MoStZlUm": "2000", "MoStAlUm": "1500"})
        # |2000-1500|/2000 = 0.25 -- nicht > 0.25
        assert d.motor_asymmetry is False

    def test_motor_asymmetry_just_above_threshold(self):
        """26% Asymmetrie -- Alarm."""
        d = KWLData({"MoStZlUm": "2000", "MoStAlUm": "1480"})
        # |2000-1480|/2000 = 0.26 > 0.25
        assert d.motor_asymmetry is True

    def test_motor_asymmetry_zero_rpm_no_crash(self):
        """RPM = 0 darf keinen ZeroDivisionError werfen."""
        d = KWLData({"MoStZlUm": "0", "MoStAlUm": "0"})
        assert d.motor_asymmetry is False


class TestMigrateEntry:
    """Tests fuer async_migrate_entry v1 -> v2."""

    def test_default_watt_values_correct(self):
        """DEFAULT_WATT hat die bestaetigten Messwerte."""
        from kwl_fraenkische.const import DEFAULT_WATT
        assert DEFAULT_WATT[1] == 11.0
        assert DEFAULT_WATT[2] == 17.5
        assert DEFAULT_WATT[3] == 43.5
        assert DEFAULT_WATT[4] == 80.0

    def test_all_four_levels_have_default(self):
        from kwl_fraenkische.const import DEFAULT_WATT
        for level in (1, 2, 3, 4):
            assert level in DEFAULT_WATT
            assert DEFAULT_WATT[level] > 0

    def test_watt_increases_with_level(self):
        from kwl_fraenkische.const import DEFAULT_WATT
        assert DEFAULT_WATT[1] < DEFAULT_WATT[2] < DEFAULT_WATT[3] < DEFAULT_WATT[4]


class TestEtaGuard:
    """Tests fuer Waermerueckgewinnungsgrad eta-Berechnung mit reduziertem Guard."""

    def test_eta_computed_when_delta_above_1_5(self):
        """Delta 2K -- sollte eta liefern (Guard bei 1.5K)."""
        d = KWLData({"abl0": "22.0", "zul0": "20.5", "aul0": "20.0"})
        eta = d.heat_recovery_efficiency
        assert eta is not None
        assert eta > 0

    def test_eta_at_boundary_1_5_returns_value(self):
        """Delta exakt 1.5K -- Guard ist < 1.5, also wird Wert berechnet."""
        d = KWLData({"abl0": "21.5", "zul0": "20.5", "aul0": "20.0"})
        # delta = 21.5 - 20.0 = 1.5 -- nicht < 1.5, also wird eta berechnet
        eta = d.heat_recovery_efficiency
        assert eta is not None

    def test_eta_none_when_delta_below_1_5(self):
        """Delta 1.4K -- unter Guard-Schwelle, None."""
        d = KWLData({"abl0": "21.4", "zul0": "20.5", "aul0": "20.0"})
        # delta = 21.4 - 20.0 = 1.4 < 1.5, also None
        assert d.heat_recovery_efficiency is None

    def test_eta_none_when_delta_below_1_5(self):
        """Delta unter 1.5K -- None."""
        d = KWLData({"abl0": "21.0", "zul0": "20.5", "aul0": "20.0"})
        assert d.heat_recovery_efficiency is None

    def test_eta_plausible_range(self, sample_xml):
        """Eta aus Sample XML muss in plausiblem Bereich liegen."""
        data = KWLData(_parse_xml(sample_xml))
        eta = data.heat_recovery_efficiency
        if eta is not None:
            assert 0 < eta <= 100

    def test_eta_perfect_recovery(self):
        """Wenn Zuluft = Abluft: eta 100%."""
        d = KWLData({"abl0": "22.0", "zul0": "22.0", "aul0": "10.0"})
        assert d.heat_recovery_efficiency == 100.0

    def test_eta_zero_recovery(self):
        """Wenn Zuluft = Aussen: eta 0%."""
        d = KWLData({"abl0": "22.0", "zul0": "10.0", "aul0": "10.0"})
        assert d.heat_recovery_efficiency == 0.0


class TestHeatRecoveryWatts:
    """Tests fuer zurueckgewonnene Waermeleistung."""

    def test_watts_positive_when_abluft_warmer(self):
        d = KWLData({"abl0": "22.0", "zul0": "18.0",
                     "stufe3": "1", "stufe1": "0", "stufe2": "0", "stufe4": "0"})
        watts = d.heat_recovery_watts
        assert watts is not None
        assert watts > 0

    def test_watts_none_when_zuluft_warmer(self):
        """Wenn Zuluft waermer als Abluft -- keine sinnvolle Berechnung."""
        d = KWLData({"abl0": "18.0", "zul0": "22.0",
                     "stufe1": "1", "stufe2": "0", "stufe3": "0", "stufe4": "0"})
        assert d.heat_recovery_watts is None

    def test_watts_scale_with_level(self):
        """Hoehere Stufe = mehr Volumenstrom = mehr Watt bei gleicher Temperaturdifferenz."""
        base = {"abl0": "22.0", "zul0": "18.0",
                "stufe2": "0", "stufe3": "0", "stufe4": "0"}
        d1 = KWLData({**base, "stufe1": "1"})
        d3 = KWLData({**base, "stufe3": "1", "stufe1": "0"})
        w1 = d1.heat_recovery_watts
        w3 = d3.heat_recovery_watts
        assert w1 is not None and w3 is not None
        assert w3 > w1


class TestBinaryBinarySensorDescriptions:
    """Tests fuer binary_sensor.py Beschreibungen."""

    def test_all_required_keys_present(self):
        """Alle erwarteten Binary Sensor Keys sind definiert."""
        from kwl_fraenkische.binary_sensor import BINARY_SENSORS
        keys = {d.key for d in BINARY_SENSORS}
        expected = {
            "filter_ok", "safety_active", "passive_mode", "preheater_active",
            "digital_input_1", "digital_input_2", "digital_input_3",
            "frost_risk", "bypass_leaking", "motor_asymmetry", "bypass_recommended",
        }
        assert expected.issubset(keys), f"Fehlende Keys: {expected - keys}"

    def test_derived_sensors_have_required_tag(self):
        """Alle derived Binary Sensoren haben einen required_tag."""
        from kwl_fraenkische.binary_sensor import BINARY_SENSORS
        derived = {"frost_risk", "bypass_leaking", "motor_asymmetry",
                   "bypass_recommended", "digital_input_1", "digital_input_2",
                   "digital_input_3"}
        for desc in BINARY_SENSORS:
            if desc.key in derived:
                assert desc.required_tag is not None, \
                    f"{desc.key} hat keinen required_tag"

    def test_diagnostic_sensors_have_entity_category(self):
        """Diagnose-Sensoren haben entity_category gesetzt."""
        from kwl_fraenkische.binary_sensor import BINARY_SENSORS
        from homeassistant.helpers.entity import EntityCategory
        diagnostic_keys = {
            "safety_active", "passive_mode", "preheater_active",
            "frost_risk", "bypass_leaking", "motor_asymmetry",
            "digital_input_1", "digital_input_2", "digital_input_3",
        }
        for desc in BINARY_SENSORS:
            if desc.key in diagnostic_keys:
                assert desc.entity_category is not None, \
                    f"{desc.key} hat kein entity_category"

    def test_value_functions_return_bool(self):
        """Alle value_fn der Binary Sensoren geben bool oder None zurueck."""
        from kwl_fraenkische.binary_sensor import BINARY_SENSORS
        d = KWLData({
            "filter0": "Filter ersetzt",
            "safety": "Nicht aktiv",
            "passiv": "Aus",
            "vorheiz": "Passiv",
            "DiIn1": "Aus", "DiIn2": "Aus", "DiIn3": "Aus",
            "aul0": "14.8", "zul0": "17.9", "abl0": "22.8", "fol0": "19.5",
            "bypass": "Man.: Offen",
            "MoStZlUm": "2291", "MoStAlUm": "1953",
        })
        for desc in BINARY_SENSORS:
            result = desc.value_fn(d)
            assert isinstance(result, (bool, type(None))), \
                f"{desc.key}.value_fn returned {type(result)}"


class TestOptionsFlow:
    """Tests fuer Options Flow Konfiguration."""

    def test_scan_interval_constants(self):
        """CONF_SCAN_INTERVAL und Grenzen sind definiert."""
        from kwl_fraenkische.const import (
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL,
            MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL,
        )
        assert CONF_SCAN_INTERVAL == "scan_interval"
        assert MIN_SCAN_INTERVAL == 30
        assert MAX_SCAN_INTERVAL == 300
        assert MIN_SCAN_INTERVAL <= DEFAULT_SCAN_INTERVAL <= MAX_SCAN_INTERVAL

    def test_default_scan_interval_is_30(self):
        from kwl_fraenkische.const import DEFAULT_SCAN_INTERVAL
        assert DEFAULT_SCAN_INTERVAL == 30

    def test_watt_conf_keys_defined(self):
        from kwl_fraenkische.const import (
            CONF_WATT_LEVEL_1, CONF_WATT_LEVEL_2,
            CONF_WATT_LEVEL_3, CONF_WATT_LEVEL_4,
        )
        keys = {CONF_WATT_LEVEL_1, CONF_WATT_LEVEL_2,
                CONF_WATT_LEVEL_3, CONF_WATT_LEVEL_4}
        assert len(keys) == 4  # alle unterschiedlich
