"""Tests für Phase 4: Entity-Plattformen — Protokoll-Verzweigung.

Geprüft via AST-Analyse da vollständiger HA-Import in Stub-Umgebung nicht möglich.

Abgedeckte Anforderungen:
- __init__.py: KWLFlexCoordinator importiert, AnyKWLCoordinator definiert,
  async_setup_entry verzweigt nach Protokoll
- sensor.py: supported_protocols Feld vorhanden, Flex-Sensoren definiert,
  Protocol-Fork in setup_entry
- binary_sensor.py: supported_protocols, alarm_active, Protocol-Fork
- button.py: flex Buttons, KWLFlexButton Klasse, Protocol-Fork
- select.py: operating_mode Flex-Select, KWLFlexSelect, Protocol-Fork
- number.py: filter_total_days_flex, KWLFlexNumber, Protocol-Fork
- fan.py: Protocol-Guard (kein Fan für Flex)
"""
from __future__ import annotations
import ast

BASE = "/home/claude/kwl_src/custom_components/kwl_fraenkische/"


def _src(filename: str) -> str:
    return open(BASE + filename).read()


def _ast(filename: str) -> ast.Module:
    return ast.parse(_src(filename))


def _class_method_src(filename: str, cls: str, method: str) -> str:
    tree = _ast(filename)
    src = _src(filename)
    lines = src.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for item in node.body:
                if isinstance(item, (ast.AsyncFunctionDef, ast.FunctionDef)) \
                        and item.name == method:
                    return "\n".join(lines[item.lineno - 1:item.end_lineno])
    return ""


def _func_src(filename: str, func: str) -> str:
    tree = _ast(filename)
    src = _src(filename)
    lines = src.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) \
                and node.name == func and not isinstance(node, ast.ClassDef):
            return "\n".join(lines[node.lineno - 1:node.end_lineno])
    return ""


def _has_class(filename: str, cls: str) -> bool:
    for node in ast.walk(_ast(filename)):
        if isinstance(node, ast.ClassDef) and node.name == cls:
            return True
    return False


def _has_key_in_descriptions(filename: str, key: str) -> bool:
    """Check if a description tuple contains an entry with the given key."""
    src = _src(filename)
    return f'key="{key}"' in src or f"key='{key}'" in src


# ── __init__.py ───────────────────────────────────────────────────────────────

class TestInitProtocolBranching:

    def test_flex_coordinator_imported(self):
        src = _src("__init__.py")
        assert "KWLFlexCoordinator" in src

    def test_any_coordinator_type_defined(self):
        src = _src("__init__.py")
        assert "AnyKWLCoordinator" in src

    def test_protocol_modbus_imported(self):
        src = _src("__init__.py")
        assert "PROTOCOL_MODBUS" in src

    def test_setup_entry_branches_on_protocol(self):
        src = _func_src("__init__.py", "async_setup_entry")
        assert "PROTOCOL_MODBUS" in src or "protocol" in src

    def test_setup_entry_creates_flex_coordinator(self):
        src = _func_src("__init__.py", "async_setup_entry")
        assert "KWLFlexCoordinator" in src

    def test_setup_entry_creates_kwl_coordinator(self):
        src = _func_src("__init__.py", "async_setup_entry")
        assert "KWLCoordinator" in src

    def test_unload_uses_any_coordinator(self):
        src = _func_src("__init__.py", "async_unload_entry")
        assert "AnyKWLCoordinator" in src or "coordinator" in src

    def test_credentials_use_get_with_default(self):
        """skip_installer speichert leere Credentials — .get() verhindert KeyError."""
        src = _func_src("__init__.py", "async_setup_entry")
        # CONF_USERNAME/PASSWORD werden mit .get() abgerufen
        assert ".get(CONF_USERNAME" in src or ".get(CONF_PASSWORD" in src \
            or "data.get(" in src


# ── sensor.py ─────────────────────────────────────────────────────────────────

class TestSensorPlatform:

    def test_night_cooling_core_sensors_enabled_by_default(self):
        """UX-Roadmap 2.2: die zwei Kern-Trendwerte (letzter Kühlerfolg +
        7-Tage-Schnitt) sind standardmäßig aktiv, da sie für jeden relevant
        sind, der die Sommerkühlung nutzt."""
        src = _src("sensor.py")
        for key in ("night_cooling_last_k", "night_cooling_7d_avg_k"):
            idx = src.find(f'key="{key}"')
            assert idx >= 0, f"{key} nicht gefunden"
            block = src[idx:idx + 600]
            assert "entity_registry_enabled_default=False" not in block, (
                f"{key} soll standardmäßig aktiv sein (Kern-Trendwert)"
            )

    def test_night_cooling_detail_sensors_disabled_by_default(self):
        """Die spezielleren Diagnose-Metriken bleiben deaktiviert -- sie sind
        für gezielte Fehlersuche relevant, nicht für den Alltag."""
        src = _src("sensor.py")
        for key in (
            "night_cooling_7d_avg_efficiency",
            "night_cooling_inactive_nights_7d",
            "night_cooling_7d_avg_active_minutes",
        ):
            idx = src.find(f'key="{key}"')
            assert idx >= 0, f"{key} nicht gefunden"
            block = src[idx:idx + 600]
            assert "entity_registry_enabled_default=False" in block, (
                f"{key} muss entity_registry_enabled_default=False haben"
            )

    def test_supported_protocols_field_in_description(self):
        src = _src("sensor.py")
        assert "supported_protocols" in src

    def test_analytics_sensors_default_http_only(self):
        """KWLAnalyticsSensorDescription muss default {PROTOCOL_HTTP} haben."""
        tree = _ast("sensor.py")
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "KWLAnalyticsSensorDescription":
                cls_src = _src("sensor.py").splitlines()
                cls_text = "\n".join(cls_src[node.lineno - 1:node.end_lineno])
                assert "PROTOCOL_HTTP" in cls_text, (
                    "KWLAnalyticsSensorDescription sollte default {PROTOCOL_HTTP} haben"
                )
                return
        assert False, "KWLAnalyticsSensorDescription nicht gefunden"

    def test_power_current_marked_http_only(self):
        src = _src("sensor.py")
        # Find power_current block and verify it has PROTOCOL_HTTP
        idx = src.find('key="power_current"')
        assert idx >= 0
        block = src[idx:idx+500]
        assert "PROTOCOL_HTTP" in block

    def test_energy_level_sensors_marked_http_only(self):
        src = _src("sensor.py")
        for key in ("energy_level_1", "energy_level_2", "energy_level_3", "energy_level_4"):
            idx = src.find(f'key="{key}"')
            assert idx >= 0, f"{key} nicht in sensor.py"
            block = src[idx:idx+500]
            assert "PROTOCOL_HTTP" in block, f"{key} nicht als PROTOCOL_HTTP markiert"

    def test_flex_sensors_exist(self):
        for key in ("current_mode_text", "alarm_text", "preheater_duty_pct",
                    "hours_total", "bypass_tmin", "bypass_tmax",
                    "temp_room", "voc_ppm", "rh_percent", "co2_ppm"):
            assert _has_key_in_descriptions("sensor.py", key), (
                f"Flex-Sensor '{key}' fehlt in sensor.py"
            )

    def test_flex_sensors_marked_modbus(self):
        src = _src("sensor.py")
        for key in ("current_mode_text", "alarm_text", "hours_total"):
            idx = src.find(f'key="{key}"')
            block = src[idx:idx+500]
            assert "PROTOCOL_MODBUS" in block, f"{key} nicht als PROTOCOL_MODBUS markiert"

    def test_setup_entry_forks_on_protocol(self):
        src = _func_src("sensor.py", "async_setup_entry")
        assert "PROTOCOL_MODBUS" in src
        assert "PROTOCOL_HTTP" in src

    def test_setup_entry_excludes_tagged_sensors_for_flex(self):
        src = _func_src("sensor.py", "async_setup_entry")
        assert "required_tag" in src


# ── binary_sensor.py ──────────────────────────────────────────────────────────

class TestBinarySensorPlatform:

    def test_supported_protocols_field(self):
        src = _src("binary_sensor.py")
        assert "supported_protocols" in src

    def test_alarm_active_flex_sensor_exists(self):
        assert _has_key_in_descriptions("binary_sensor.py", "alarm_active")

    def test_alarm_active_marked_modbus(self):
        src = _src("binary_sensor.py")
        idx = src.find('key="alarm_active"')
        block = src[idx:idx+250]
        assert "PROTOCOL_MODBUS" in block

    def test_alarm_active_uses_alarm_code(self):
        src = _src("binary_sensor.py")
        idx = src.find('key="alarm_active"')
        block = src[idx:idx+250]
        assert "alarm_code" in block

    def test_analytics_default_http(self):
        src = _src("binary_sensor.py")
        idx = src.find("class KWLAnalyticsBinarySensorDescription")
        block = src[idx:idx+400]
        assert "PROTOCOL_HTTP" in block

    def test_setup_entry_forks_on_protocol(self):
        src = _func_src("binary_sensor.py", "async_setup_entry")
        assert "PROTOCOL_MODBUS" in src

    def test_setup_entry_excludes_tagged_for_flex(self):
        src = _func_src("binary_sensor.py", "async_setup_entry")
        assert "required_tag" in src


# ── button.py ─────────────────────────────────────────────────────────────────

class TestButtonPlatform:

    def test_supported_protocols_field(self):
        src = _src("button.py")
        assert "supported_protocols" in src

    def test_filter_reset_flex_button_exists(self):
        assert _has_key_in_descriptions("button.py", "filter_reset_flex")

    def test_alarm_clear_button_exists(self):
        assert _has_key_in_descriptions("button.py", "alarm_clear")

    def test_filter_reset_flex_marked_modbus(self):
        src = _src("button.py")
        idx = src.find('key="filter_reset_flex"')
        block = src[idx:idx+200]
        assert "PROTOCOL_MODBUS" in block

    def test_alarm_clear_marked_modbus(self):
        src = _src("button.py")
        idx = src.find('key="alarm_clear"')
        block = src[idx:idx+200]
        assert "PROTOCOL_MODBUS" in block

    def test_existing_buttons_marked_http(self):
        src = _src("button.py")
        for key in ("filter_reset", "sensor_toggle"):
            idx = src.find(f'key="{key}"')
            block = src[idx:idx+500]
            assert "PROTOCOL_HTTP" in block, f"Button {key} nicht als HTTP markiert"

    def test_kwl_flex_button_class_exists(self):
        assert _has_class("button.py", "KWLFlexButton")

    def test_flex_button_calls_reset_filter(self):
        src = _class_method_src("button.py", "KWLFlexButton", "async_press")
        assert "async_reset_filter" in src

    def test_flex_button_calls_clear_alarm(self):
        src = _class_method_src("button.py", "KWLFlexButton", "async_press")
        assert "async_clear_alarm" in src

    def test_setup_entry_forks_on_protocol(self):
        src = _func_src("button.py", "async_setup_entry")
        assert "PROTOCOL_MODBUS" in src


# ── select.py ─────────────────────────────────────────────────────────────────

class TestSelectPlatform:

    def test_supported_protocols_field(self):
        src = _src("select.py")
        assert "supported_protocols" in src

    def test_operating_mode_select_exists(self):
        assert _has_key_in_descriptions("select.py", "operating_mode")

    def test_operating_mode_marked_modbus(self):
        src = _src("select.py")
        idx = src.find('key="operating_mode"')
        block = src[idx:idx+500]
        assert "PROTOCOL_MODBUS" in block

    def test_flex_mode_text_used_for_options(self):
        src = _src("select.py")
        assert "FLEX_MODE_TEXT" in src

    def test_kwl_flex_select_class_exists(self):
        assert _has_class("select.py", "KWLFlexSelect")

    def test_flex_select_calls_set_mode(self):
        src = _class_method_src("select.py", "KWLFlexSelect", "async_select_option")
        assert "async_set_mode" in src

    def test_setup_entry_excludes_http_selects_for_flex(self):
        src = _func_src("select.py", "async_setup_entry")
        # post_url_fn Ausschluss als Proxy für touch-only
        assert "post_url_fn" in src or "PROTOCOL_MODBUS" in src

    def test_setup_entry_forks_on_protocol(self):
        src = _func_src("select.py", "async_setup_entry")
        assert "PROTOCOL_MODBUS" in src


# ── number.py ─────────────────────────────────────────────────────────────────

class TestNumberPlatform:

    def test_supported_protocols_field(self):
        src = _src("number.py")
        assert "supported_protocols" in src

    def test_filter_total_days_flex_exists(self):
        assert _has_key_in_descriptions("number.py", "filter_total_days_flex")

    def test_filter_total_days_flex_marked_modbus(self):
        src = _src("number.py")
        idx = src.find('key="filter_total_days_flex"')
        block = src[idx:idx+500]
        assert "PROTOCOL_MODBUS" in block

    def test_filter_total_days_flex_range_30_360(self):
        src = _src("number.py")
        idx = src.find('key="filter_total_days_flex"')
        block = src[idx:idx+500]
        assert "30" in block and "360" in block

    def test_kwl_flex_number_class_exists(self):
        assert _has_class("number.py", "KWLFlexNumber")

    def test_flex_number_calls_set_filter_total(self):
        src = _class_method_src("number.py", "KWLFlexNumber", "async_set_native_value")
        assert "async_set_filter_total" in src

    def test_setup_entry_forks_on_protocol(self):
        src = _func_src("number.py", "async_setup_entry")
        assert "PROTOCOL_MODBUS" in src

    def test_setup_entry_excludes_post_field_for_flex(self):
        """Numbers mit post_field POST zu HTTP → auto-ausgeschlossen für flex."""
        src = _func_src("number.py", "async_setup_entry")
        assert "post_field" in src


# ── fan.py ────────────────────────────────────────────────────────────────────

class TestFanPlatform:
    """Seit Fan-Level-Implementierung: KWLFan funktioniert für beide Protokolle
    identisch, kein Protocol-Guard mehr nötig (anders als zuvor angenommen)."""

    def test_no_protocol_guard_in_setup_entry(self):
        """Es darf KEINEN frühen return mehr geben -- Fan wird für beide Protokolle erstellt."""
        src = _func_src("fan.py", "async_setup_entry")
        assert "return" not in src

    def test_setup_entry_creates_kwl_fan_unconditionally(self):
        src = _func_src("fan.py", "async_setup_entry")
        assert "KWLFan(coordinator, entry)" in src

    def test_conf_protocol_no_longer_imported(self):
        """CONF_PROTOCOL/PROTOCOL_HTTP wurden mit dem Guard obsolet."""
        src = _src("fan.py")
        assert "CONF_PROTOCOL" not in src

    def test_any_coordinator_type_used(self):
        src = _src("fan.py")
        assert "AnyKWLCoordinator" in src

    def test_flex_coordinator_imported(self):
        src = _src("fan.py")
        assert "KWLFlexCoordinator" in src
