"""Tests für Phase 1: const.py Erweiterungen und manifest.json.

Abgedeckte Anforderungen (IMPLEMENTIERUNGSPLAN.md Phase 1):
- Alle neuen Modell-IDs korrekt definiert
- MODEL_PROTOCOLS vollständig und konsistent
- UNIT_TYPE_TO_MODEL korrekt (4/11/15)
- WATT_DEFAULTS: flex-Einträge alle None
- WATT_MAX: nur für flex-Modelle mit bekanntem Limit
- FLEX_ALARM_TEXT: alle 16 Einträge (0–15)
- FLEX_MODE_TEXT: alle bekannten Modi
- FLEX_MODE_TO_WRITE: konsistent mit FLEX_MODE_TEXT
- FLEX_MODE_TO_END: Ende-Bitmasks korrekt (0x8000 | Start)
- DEFAULT_MODBUS_PORT: 502
- manifest.json VERSION 2.0.0 und pymodbus>=3.10.0
"""
from __future__ import annotations
import json
import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _const():
    """Importiert const.py frisch (ohne HA-Abhängigkeiten)."""
    import importlib
    import sys
    # const.py hat keine HA-Importe — direkt importierbar
    if "custom_components.kwl_fraenkische.const" in sys.modules:
        return sys.modules["custom_components.kwl_fraenkische.const"]
    return importlib.import_module("custom_components.kwl_fraenkische.const")


MANIFEST_PATH = (
    "/home/claude/kwl_src/custom_components/kwl_fraenkische/manifest.json"
)


# ── Tests: Protokoll-Konstanten ────────────────────────────────────────────────

class TestProtocolConstants:
    def test_protocol_http(self):
        c = _const()
        assert c.PROTOCOL_HTTP == "http"

    def test_protocol_modbus(self):
        c = _const()
        assert c.PROTOCOL_MODBUS == "modbus"

    def test_conf_protocol_key(self):
        c = _const()
        assert c.CONF_PROTOCOL == "protocol"


# ── Tests: Flex-Modell-Identifier ─────────────────────────────────────────────

class TestFlexModelIds:
    def test_250_flex_defined(self):
        c = _const()
        assert c.MODEL_PROFI_AIR_250_FLEX == "profi_air_250_flex"

    def test_360_flex_defined(self):
        c = _const()
        assert c.MODEL_PROFI_AIR_360_FLEX == "profi_air_360_flex"

    def test_180_flat_defined(self):
        c = _const()
        assert c.MODEL_PROFI_AIR_180_FLAT == "profi_air_180_flat"

    def test_existing_touch_models_unchanged(self):
        """Bestehende Touch-Modell-IDs dürfen sich nicht verändert haben."""
        c = _const()
        assert c.MODEL_PROFI_AIR_250 == "profi_air_250"
        assert c.MODEL_PROFI_AIR_400 == "profi_air_400"
        assert c.DEFAULT_MODEL == c.MODEL_PROFI_AIR_400


# ── Tests: MODEL_PROTOCOLS ────────────────────────────────────────────────────

class TestModelProtocols:
    def test_touch_models_use_http(self):
        c = _const()
        assert c.MODEL_PROTOCOLS[c.MODEL_PROFI_AIR_250] == c.PROTOCOL_HTTP
        assert c.MODEL_PROTOCOLS[c.MODEL_PROFI_AIR_400] == c.PROTOCOL_HTTP

    def test_flex_models_use_modbus(self):
        c = _const()
        assert c.MODEL_PROTOCOLS[c.MODEL_PROFI_AIR_250_FLEX] == c.PROTOCOL_MODBUS
        assert c.MODEL_PROTOCOLS[c.MODEL_PROFI_AIR_360_FLEX] == c.PROTOCOL_MODBUS

    def test_180_flat_uses_modbus(self):
        c = _const()
        assert c.MODEL_PROTOCOLS[c.MODEL_PROFI_AIR_180_FLAT] == c.PROTOCOL_MODBUS

    def test_all_models_have_protocol(self):
        """Jedes bekannte Modell hat einen Protokoll-Eintrag."""
        c = _const()
        all_models = [
            c.MODEL_PROFI_AIR_250, c.MODEL_PROFI_AIR_400,
            c.MODEL_PROFI_AIR_250_FLEX, c.MODEL_PROFI_AIR_360_FLEX,
            c.MODEL_PROFI_AIR_180_FLAT,
        ]
        for model in all_models:
            assert model in c.MODEL_PROTOCOLS, f"{model} fehlt in MODEL_PROTOCOLS"

    def test_only_valid_protocol_values(self):
        """Nur bekannte Protokoll-Strings erlaubt."""
        c = _const()
        valid = {c.PROTOCOL_HTTP, c.PROTOCOL_MODBUS}
        for model, proto in c.MODEL_PROTOCOLS.items():
            assert proto in valid, f"{model}: unbekanntes Protokoll '{proto}'"


# ── Tests: UNIT_TYPE_TO_MODEL ─────────────────────────────────────────────────

class TestUnitTypeToModel:
    def test_type_4_is_180_flat(self):
        c = _const()
        assert c.UNIT_TYPE_TO_MODEL[4] == c.MODEL_PROFI_AIR_180_FLAT

    def test_type_11_is_250_flex(self):
        c = _const()
        assert c.UNIT_TYPE_TO_MODEL[11] == c.MODEL_PROFI_AIR_250_FLEX

    def test_type_15_is_360_flex(self):
        c = _const()
        assert c.UNIT_TYPE_TO_MODEL[15] == c.MODEL_PROFI_AIR_360_FLEX

    def test_only_known_types(self):
        """Nur dokumentierte Unit-Typ-Codes (4, 11, 15)."""
        c = _const()
        assert set(c.UNIT_TYPE_TO_MODEL.keys()) == {4, 11, 15}

    def test_all_values_are_modbus_models(self):
        """Alle Werte müssen Modbus-Modelle sein."""
        c = _const()
        for unit_type, model in c.UNIT_TYPE_TO_MODEL.items():
            assert c.MODEL_PROTOCOLS.get(model) == c.PROTOCOL_MODBUS, (
                f"UNIT_TYPE_TO_MODEL[{unit_type}]={model!r} ist kein Modbus-Modell"
            )


# ── Tests: MODEL_DISPLAY ─────────────────────────────────────────────────────

class TestModelDisplay:
    def test_all_models_have_display_name(self):
        c = _const()
        for model in c.MODEL_PROTOCOLS:
            assert model in c.MODEL_DISPLAY, f"Kein Display-Name für {model}"

    def test_display_names_not_empty(self):
        c = _const()
        for model, name in c.MODEL_DISPLAY.items():
            assert isinstance(name, str) and name, f"Leerer Name für {model}"

    def test_180_flat_marked_experimental(self):
        c = _const()
        name = c.MODEL_DISPLAY[c.MODEL_PROFI_AIR_180_FLAT]
        assert "experimentell" in name.lower(), (
            "180 flat Display-Name sollte 'experimentell' enthalten"
        )


# ── Tests: WATT_DEFAULTS ─────────────────────────────────────────────────────

class TestWattDefaults:
    def test_touch_400_values_unchanged(self):
        """Gemessene 400 touch Werte dürfen nicht geändert werden."""
        c = _const()
        w = c.WATT_DEFAULTS[c.MODEL_PROFI_AIR_400]
        assert w[1] == 11.0
        assert w[2] == 17.5
        assert w[3] == 43.5
        assert w[4] == 80.0

    def test_touch_250_values_unchanged(self):
        c = _const()
        w = c.WATT_DEFAULTS[c.MODEL_PROFI_AIR_250]
        assert w[1] == 4.0
        assert w[2] == 8.0
        assert w[3] == 23.0
        assert w[4] == 45.0

    def test_flex_250_all_none(self):
        c = _const()
        w = c.WATT_DEFAULTS[c.MODEL_PROFI_AIR_250_FLEX]
        assert all(v is None for v in w.values()), (
            "250 flex Watt-Werte müssen None sein bis gemessen"
        )

    def test_flex_360_all_none(self):
        c = _const()
        w = c.WATT_DEFAULTS[c.MODEL_PROFI_AIR_360_FLEX]
        assert all(v is None for v in w.values())

    def test_flat_180_all_none(self):
        c = _const()
        w = c.WATT_DEFAULTS[c.MODEL_PROFI_AIR_180_FLAT]
        assert all(v is None for v in w.values())

    def test_all_models_have_four_levels(self):
        """Alle Modelle haben Einträge für Stufen 1–4."""
        c = _const()
        for model, watt in c.WATT_DEFAULTS.items():
            assert set(watt.keys()) == {1, 2, 3, 4}, (
                f"{model}: WATT_DEFAULTS muss Stufen 1-4 haben"
            )


# ── Tests: WATT_MAX ───────────────────────────────────────────────────────────

class TestWattMax:
    def test_250_flex_max(self):
        c = _const()
        assert c.WATT_MAX[c.MODEL_PROFI_AIR_250_FLEX] == 170.0

    def test_360_flex_max(self):
        c = _const()
        assert c.WATT_MAX[c.MODEL_PROFI_AIR_360_FLEX] == 230.0

    def test_180_flat_not_in_watt_max(self):
        """180 flat hat keinen validierten Max-Wert → kein Eintrag."""
        c = _const()
        assert c.MODEL_PROFI_AIR_180_FLAT not in c.WATT_MAX

    def test_touch_models_not_in_watt_max(self):
        """Touch-Modelle haben kein Datenblatt-Limit definiert."""
        c = _const()
        assert c.MODEL_PROFI_AIR_250 not in c.WATT_MAX
        assert c.MODEL_PROFI_AIR_400 not in c.WATT_MAX


# ── Tests: FLEX_ALARM_TEXT ────────────────────────────────────────────────────

class TestFlexAlarmText:
    def test_zero_is_no_alarm(self):
        c = _const()
        assert c.FLEX_ALARM_TEXT[0] == ""

    def test_all_codes_0_to_15(self):
        c = _const()
        assert set(c.FLEX_ALARM_TEXT.keys()) == set(range(16))

    def test_e1_exhaust_fan(self):
        c = _const()
        assert "E1" in c.FLEX_ALARM_TEXT[1]
        assert "Abluft" in c.FLEX_ALARM_TEXT[1]

    def test_e2_supply_fan(self):
        c = _const()
        assert "E2" in c.FLEX_ALARM_TEXT[2]
        assert "Zuluft" in c.FLEX_ALARM_TEXT[2]

    def test_e11_frost(self):
        c = _const()
        assert "E11" in c.FLEX_ALARM_TEXT[11]
        # Frostgefahr oder Zuluft < 5°C
        assert "°C" in c.FLEX_ALARM_TEXT[11] or "Frost" in c.FLEX_ALARM_TEXT[11]

    def test_all_non_zero_texts_start_with_e(self):
        c = _const()
        for code, text in c.FLEX_ALARM_TEXT.items():
            if code > 0:
                assert text.startswith("E"), (
                    f"Alarm-Code {code}: Text sollte mit 'E' beginnen, ist: {text!r}"
                )

    def test_all_texts_are_strings(self):
        c = _const()
        for code, text in c.FLEX_ALARM_TEXT.items():
            assert isinstance(text, str), f"Alarm-Code {code}: kein String"


# ── Tests: FLEX_MODE_TEXT ─────────────────────────────────────────────────────

class TestFlexModeText:
    def test_mode_1_manual(self):
        c = _const()
        assert c.FLEX_MODE_TEXT[1] == "Manuell"

    def test_mode_2_demand(self):
        c = _const()
        assert c.FLEX_MODE_TEXT[2] == "Bedarfsgesteuert"

    def test_mode_3_week_program(self):
        c = _const()
        assert c.FLEX_MODE_TEXT[3] == "Wochenprogramm"

    def test_all_values_are_nonempty_strings(self):
        c = _const()
        for code, text in c.FLEX_MODE_TEXT.items():
            assert isinstance(text, str) and text, (
                f"Modus {code}: leerer oder kein String"
            )


# ── Tests: FLEX_MODE_TO_WRITE ─────────────────────────────────────────────────

class TestFlexModeToWrite:
    def test_manual_bitmask(self):
        c = _const()
        assert c.FLEX_MODE_TO_WRITE["Manuell"] == 0x0004

    def test_demand_bitmask(self):
        c = _const()
        assert c.FLEX_MODE_TO_WRITE["Bedarfsgesteuert"] == 0x0002

    def test_week_program_bitmask(self):
        c = _const()
        assert c.FLEX_MODE_TO_WRITE["Wochenprogramm"] == 0x0008

    def test_all_mode_texts_have_write_bitmask(self):
        """Jeder anzeigebare Modus muss auch schreibbar sein."""
        c = _const()
        for mode_name in c.FLEX_MODE_TEXT.values():
            assert mode_name in c.FLEX_MODE_TO_WRITE, (
                f"'{mode_name}' in FLEX_MODE_TEXT aber nicht in FLEX_MODE_TO_WRITE"
            )

    def test_bitmasks_are_positive_ints(self):
        c = _const()
        for name, mask in c.FLEX_MODE_TO_WRITE.items():
            assert isinstance(mask, int) and mask > 0, (
                f"Modus '{name}': Bitmask muss positive int sein, ist: {mask!r}"
            )

    def test_end_bitmasks_are_8000_or(self):
        """End-Bitmasks = 0x8000 | Start-Bitmask."""
        c = _const()
        for mode, end_mask in c.FLEX_MODE_TO_END.items():
            if mode in c.FLEX_MODE_TO_WRITE:
                start_mask = c.FLEX_MODE_TO_WRITE[mode]
                expected = 0x8000 | start_mask
                assert end_mask == expected, (
                    f"End-Bitmask für '{mode}' sollte 0x{expected:04X} sein, "
                    f"ist 0x{end_mask:04X}"
                )


# ── Tests: Modbus-Konstanten ──────────────────────────────────────────────────

class TestModbusConstants:
    def test_default_port_502(self):
        c = _const()
        assert c.DEFAULT_MODBUS_PORT == 502

    def test_flex_level_ratios(self):
        c = _const()
        assert c.FLEX_LEVEL_RATIO[1] == pytest.approx(0.49)
        assert c.FLEX_LEVEL_RATIO[2] == pytest.approx(0.70)
        assert c.FLEX_LEVEL_RATIO[3] == pytest.approx(1.00)
        assert set(c.FLEX_LEVEL_RATIO.keys()) == {1, 2, 3, 4}


# ── Tests: manifest.json ──────────────────────────────────────────────────────

class TestManifest:
    def _load(self):
        return json.loads(open(MANIFEST_PATH).read())

    def test_version_is_2_0_2(self):
        m = self._load()
        assert m["version"] == "2.0.2"

    def test_pymodbus_in_requirements(self):
        m = self._load()
        reqs = m.get("requirements", [])
        assert any("pymodbus" in r for r in reqs), (
            f"pymodbus fehlt in requirements: {reqs}"
        )

    def test_pymodbus_version_constraint(self):
        m = self._load()
        pymodbus_req = next(
            (r for r in m.get("requirements", []) if "pymodbus" in r), None
        )
        assert pymodbus_req is not None
        assert ">=" in pymodbus_req, (
            f"pymodbus requirement ohne Versionsconstraint: {pymodbus_req!r}"
        )
        # Mindestversion muss >= 3.10.0 sein
        version_str = pymodbus_req.split(">=")[1].strip()
        parts = [int(x) for x in version_str.split(".")]
        assert parts >= [3, 10, 0], (
            f"pymodbus Mindestversion zu alt: {version_str}"
        )

    def test_domain_unchanged(self):
        m = self._load()
        assert m["domain"] == "kwl_fraenkische"

    def test_quality_scale_platinum(self):
        m = self._load()
        assert m["quality_scale"] == "platinum"

    def test_codeowners_set(self):
        m = self._load()
        assert "@johnnyh1975" in m.get("codeowners", [])
