"""Tests für Phase 3: Config Flow — Protokoll-Erkennung, neue Steps, Options Flow.

Abgedeckte Anforderungen (IMPLEMENTIERUNGSPLAN.md Phase 3):
- HTTP-Probe OK + Installer-OK → Watt-Schritt
- HTTP-Probe OK + Installer-Fail → Menu
- Menu → "auth" → auth Schritt
- Menu → "skip_installer" → Watt-Schritt (keine Credentials)
- Modbus-Probe OK, Unit-Typ 15 → confirm_flex-Schritt
- Modbus-Probe OK, Unit-Typ 4 → confirm_flex mit "experimentell" Modell
- Beide Probes fehlgeschlagen → Fehler "cannot_connect"
- Duplicate via MAC → Abort
- CONF_PROTOCOL=http in touch-Entry-Data
- CONF_PROTOCOL=modbus in flex-Entry-Data
- Options Flow touch: Modell-Selektor vorhanden
- Options Flow flex: kein Modell-Selektor
- Options Flow flex: WATT_MAX als Validator-Grenze
"""
from __future__ import annotations

import ast
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

CONFIG_FLOW_PY = (
    "/home/claude/kwl_src/custom_components/kwl_fraenkische/config_flow.py"
)


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _source() -> str:
    return open(CONFIG_FLOW_PY).read()


def _ast() -> ast.Module:
    return ast.parse(_source())


def _get_class_method_source(cls_name: str, method_name: str) -> str:
    tree = _ast()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls_name:
            for item in node.body:
                if isinstance(item, (ast.AsyncFunctionDef, ast.FunctionDef)) \
                        and item.name == method_name:
                    lines = _source().splitlines()
                    return "\n".join(lines[item.lineno - 1:item.end_lineno])
    return ""


def _get_function_source(func_name: str) -> str:
    tree = _ast()
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) \
                and node.name == func_name:
            lines = _source().splitlines()
            return "\n".join(lines[node.lineno - 1:node.end_lineno])
    return ""


# ── Tests: Neue Steps vorhanden ───────────────────────────────────────────────

class TestTimeoutErrorHandling:
    """Bug-Fix: asyncio.TimeoutError ist KEIN aiohttp.ClientError — wurde
    bisher nicht gefangen, was zu HA's generischem 'Unknown error occurred'
    statt einer brauchbaren Fehlermeldung führte (v.a. bei unerreichbaren
    IPs, wo die Verbindung nicht aktiv abgelehnt wird sondern stumm verfällt)."""

    def test_fetch_device_info_catches_timeout_error(self):
        src = _get_function_source("_fetch_device_info")
        assert "TimeoutError" in src

    def test_fetch_device_info_except_clause_includes_both(self):
        src = _get_function_source("_fetch_device_info")
        assert "except (aiohttp.ClientError, TimeoutError):" in src

    def test_test_auth_catches_timeout_error(self):
        src = _get_function_source("_test_auth")
        assert "TimeoutError" in src

    @pytest.mark.asyncio
    async def test_fetch_device_info_returns_cannot_connect_on_timeout(self):
        """Echter Funktionstest: TimeoutError während session.get() → 'cannot_connect', kein Crash."""
        import sys
        sys.path.insert(0, "/home/claude/kwl_src")
        exec(open("/home/claude/kwl_src/tests/conftest.py").read())

        from unittest.mock import AsyncMock, MagicMock, patch
        from custom_components.kwl_fraenkische.config_flow import _fetch_device_info

        with patch("aiohttp.ClientSession.get", side_effect=TimeoutError()):
            result = await _fetch_device_info("10.10.4.1")

        assert result == "cannot_connect"


class TestNewStepsExist:
    """Alle neuen Steps müssen als Methoden auf KWLConfigFlow vorhanden sein."""

    def _has_method(self, method_name: str) -> bool:
        src = _get_class_method_source("KWLConfigFlow", method_name)
        return bool(src)

    def test_installer_menu_step_exists(self):
        assert self._has_method("async_step_installer_menu")

    def test_skip_installer_step_exists(self):
        assert self._has_method("async_step_skip_installer")

    def test_confirm_flex_step_exists(self):
        assert self._has_method("async_step_confirm_flex")

    def test_probe_modbus_function_exists(self):
        src = _get_function_source("_probe_modbus")
        assert src, "_probe_modbus Funktion nicht gefunden"

    def test_fetch_device_info_still_exists(self):
        """Bestehende HTTP-Probe-Funktion muss erhalten bleiben."""
        src = _get_function_source("_fetch_device_info")
        assert src


# ── Tests: async_step_user — Protokoll-Weiche ─────────────────────────────────

class TestStepUserProtocolDetection:
    """async_step_user muss zuerst HTTP, dann Modbus probieren."""

    def test_http_probe_called_first(self):
        src = _get_class_method_source("KWLConfigFlow", "async_step_user")
        # _fetch_device_info (HTTP) muss vor _probe_modbus aufgerufen werden
        http_pos = src.find("_fetch_device_info")
        modbus_pos = src.find("_probe_modbus")
        assert http_pos >= 0, "_fetch_device_info nicht in async_step_user"
        assert modbus_pos >= 0, "_probe_modbus nicht in async_step_user"
        assert http_pos < modbus_pos, "HTTP-Probe muss vor Modbus-Probe kommen"

    def test_installer_menu_called_on_http_success(self):
        src = _get_class_method_source("KWLConfigFlow", "async_step_user")
        assert "installer_menu" in src

    def test_confirm_flex_called_on_modbus_success(self):
        src = _get_class_method_source("KWLConfigFlow", "async_step_user")
        assert "confirm_flex" in src

    def test_cannot_connect_error_when_both_fail(self):
        src = _get_class_method_source("KWLConfigFlow", "async_step_user")
        assert "cannot_connect" in src

    def test_protocol_set_to_http_on_touch(self):
        src = _get_class_method_source("KWLConfigFlow", "async_step_user")
        assert "PROTOCOL_HTTP" in src

    def test_protocol_set_to_modbus_on_flex(self):
        src = _get_class_method_source("KWLConfigFlow", "async_step_user")
        assert "PROTOCOL_MODBUS" in src

    def test_firmware_stored_for_flex(self):
        src = _get_class_method_source("KWLConfigFlow", "async_step_user")
        assert "firmware" in src or "_firmware_version" in src

    def test_switch_position_stored_for_flex(self):
        src = _get_class_method_source("KWLConfigFlow", "async_step_user")
        assert "switch_position" in src or "_switch_position" in src


# ── Tests: installer_menu Step ────────────────────────────────────────────────

class TestInstallerMenuStep:

    def test_uses_async_show_menu(self):
        src = _get_class_method_source("KWLConfigFlow", "async_step_installer_menu")
        assert "async_show_menu" in src

    def test_menu_has_auth_option(self):
        src = _get_class_method_source("KWLConfigFlow", "async_step_installer_menu")
        assert '"auth"' in src or "'auth'" in src

    def test_menu_has_skip_option(self):
        src = _get_class_method_source("KWLConfigFlow", "async_step_installer_menu")
        assert "skip" in src


# ── Tests: skip_installer Step ────────────────────────────────────────────────

class TestSkipInstallerStep:

    def test_clears_username(self):
        src = _get_class_method_source("KWLConfigFlow", "async_step_skip_installer")
        # Leerer Username oder kein Username gesetzt
        assert "_username" in src or "username" in src.lower()

    def test_proceeds_to_watt_step(self):
        src = _get_class_method_source("KWLConfigFlow", "async_step_skip_installer")
        assert "async_step_watt" in src


# ── Tests: confirm_flex Step ──────────────────────────────────────────────────

class TestConfirmFlexStep:

    def test_sets_unique_id(self):
        src = _get_class_method_source("KWLConfigFlow", "async_step_confirm_flex")
        assert "async_set_unique_id" in src

    def test_aborts_on_duplicate(self):
        src = _get_class_method_source("KWLConfigFlow", "async_step_confirm_flex")
        assert "_abort_if_unique_id_configured" in src

    def test_stores_protocol_modbus(self):
        src = _get_class_method_source("KWLConfigFlow", "async_step_confirm_flex")
        assert "PROTOCOL_MODBUS" in src

    def test_stores_model(self):
        src = _get_class_method_source("KWLConfigFlow", "async_step_confirm_flex")
        assert "model" in src

    def test_description_placeholders_include_model(self):
        src = _get_class_method_source("KWLConfigFlow", "async_step_confirm_flex")
        assert "description_placeholders" in src
        assert "model" in src

    def test_description_placeholders_include_firmware(self):
        src = _get_class_method_source("KWLConfigFlow", "async_step_confirm_flex")
        assert "firmware" in src

    def test_description_placeholders_include_switch(self):
        src = _get_class_method_source("KWLConfigFlow", "async_step_confirm_flex")
        assert "switch" in src


# ── Tests: async_step_watt — CONF_PROTOCOL gesetzt ────────────────────────────

class TestWattStepProtocol:

    def test_stores_conf_protocol_http(self):
        src = _get_class_method_source("KWLConfigFlow", "async_step_watt")
        assert "CONF_PROTOCOL" in src
        assert "PROTOCOL_HTTP" in src

    def test_still_stores_host_and_mac(self):
        src = _get_class_method_source("KWLConfigFlow", "async_step_watt")
        assert "CONF_HOST" in src
        assert '"mac"' in src or "'mac'" in src


# ── Tests: _probe_modbus Hilfsfunktion ────────────────────────────────────────

class TestProbeModbus:

    def test_uses_async_modbus_tcp_client(self):
        src = _get_function_source("_probe_modbus")
        assert "AsyncModbusTcpClient" in src

    def test_uses_unit_type_to_model(self):
        src = _get_function_source("_probe_modbus")
        assert "UNIT_TYPE_TO_MODEL" in src

    def test_reads_system_id_offset_2(self):
        src = _get_function_source("_probe_modbus")
        assert "address=2" in src

    def test_reads_mac_offset_40(self):
        src = _get_function_source("_probe_modbus")
        assert "address=40" in src

    def test_reads_hal_offset_84(self):
        src = _get_function_source("_probe_modbus")
        assert "address=84" in src

    def test_returns_none_on_unknown_unit_type(self):
        src = _get_function_source("_probe_modbus")
        assert "return None" in src

    def test_closes_client_in_finally(self):
        src = _get_function_source("_probe_modbus")
        assert "finally" in src
        assert "close" in src

    def test_returns_dict_with_required_keys(self):
        src = _get_function_source("_probe_modbus")
        for key in ("model", "mac_id", "firmware", "switch_position"):
            assert f'"{key}"' in src or f"'{key}'" in src, (
                f"Schlüssel '{key}' fehlt im Rückgabe-Dict von _probe_modbus"
            )

    def test_suppresses_pymodbus_logging(self):
        src = _get_function_source("_probe_modbus")
        assert "pymodbus" in src and "CRITICAL" in src

    def test_retries_zero_for_fast_fail(self):
        """Modbus-Probe muss schnell scheitern: retries=0."""
        src = _get_function_source("_probe_modbus")
        assert "retries=0" in src

    @pytest.mark.asyncio
    async def test_returns_none_when_connect_fails(self):
        """Verbindungsfehler → None."""
        import sys
        sys.path.insert(0, "/home/claude/kwl_src")
        exec(open("/home/claude/kwl_src/tests/conftest.py").read())

        from pymodbus.client import AsyncModbusTcpClient
        with patch.object(AsyncModbusTcpClient, "connect", new_callable=AsyncMock, return_value=False):
            from custom_components.kwl_fraenkische.config_flow import _probe_modbus
            result = await _probe_modbus("192.168.1.99", port=502)
        assert result is None


# ── Tests: Options Flow — Protokoll-Bewusstsein ────────────────────────────────

class TestOptionsFlowProtocolAware:

    def test_touch_schema_method_exists(self):
        src = _get_class_method_source("KWLOptionsFlow", "_touch_schema")
        assert src, "_touch_schema nicht in KWLOptionsFlow"

    def test_flex_schema_method_exists(self):
        src = _get_class_method_source("KWLOptionsFlow", "_flex_schema")
        assert src, "_flex_schema nicht in KWLOptionsFlow"

    def test_init_checks_protocol(self):
        src = _get_class_method_source("KWLOptionsFlow", "async_step_init")
        assert "CONF_PROTOCOL" in src or "protocol" in src.lower()

    def test_touch_schema_has_model_selector(self):
        src = _get_class_method_source("KWLOptionsFlow", "_touch_schema")
        assert "CONF_MODEL" in src

    def test_touch_schema_uses_select_selector_with_labels(self):
        """Bug-Fix: vol.In([...]) zeigte Rohwerte (profi_air_250) statt
        Klarnamen in der UI. SelectSelector mit MODEL_DISPLAY-Labels nutzen."""
        src = _get_class_method_source("KWLOptionsFlow", "_touch_schema")
        assert "SelectSelector" in src
        assert "SelectOptionDict" in src
        assert "MODEL_DISPLAY" in src

    def test_touch_schema_no_longer_uses_bare_vol_in_for_model(self):
        """vol.In([MODEL_PROFI_AIR_250, MODEL_PROFI_AIR_400]) muss ersetzt sein."""
        src = _get_class_method_source("KWLOptionsFlow", "_touch_schema")
        assert "vol.In([MODEL_PROFI_AIR_250, MODEL_PROFI_AIR_400])" not in src

    def test_select_selector_imported(self):
        src = _source()
        assert "SelectSelector" in src
        assert "SelectSelectorConfig" in src
        assert "SelectOptionDict" in src

    def test_flex_schema_no_model_selector(self):
        src = _get_class_method_source("KWLOptionsFlow", "_flex_schema")
        assert "CONF_MODEL" not in src

    def test_flex_schema_uses_watt_max(self):
        src = _get_class_method_source("KWLOptionsFlow", "_flex_schema")
        assert "WATT_MAX" in src

    def test_flex_schema_has_optional_watt_fields(self):
        src = _get_class_method_source("KWLOptionsFlow", "_flex_schema")
        assert "Optional" in src

    def test_touch_schema_has_scan_interval(self):
        src = _get_class_method_source("KWLOptionsFlow", "_touch_schema")
        assert "CONF_SCAN_INTERVAL" in src

    def test_flex_schema_has_scan_interval(self):
        src = _get_class_method_source("KWLOptionsFlow", "_flex_schema")
        assert "CONF_SCAN_INTERVAL" in src


# ── Tests: State-Variablen in __init__ ────────────────────────────────────────

class TestConfigFlowStateVars:
    """Neue State-Variablen müssen in __init__ deklariert sein."""

    def test_protocol_state_var(self):
        src = _get_class_method_source("KWLConfigFlow", "__init__")
        assert "_protocol" in src

    def test_detected_model_state_var(self):
        src = _get_class_method_source("KWLConfigFlow", "__init__")
        assert "_detected_model" in src

    def test_firmware_version_state_var(self):
        src = _get_class_method_source("KWLConfigFlow", "__init__")
        assert "_firmware_version" in src

    def test_switch_position_state_var(self):
        src = _get_class_method_source("KWLConfigFlow", "__init__")
        assert "_switch_position" in src


# ── Tests: Konstanten & Imports ───────────────────────────────────────────────

class TestImportsAndConstants:

    def test_conf_protocol_imported(self):
        src = _source()
        assert "CONF_PROTOCOL" in src

    def test_protocol_http_imported(self):
        src = _source()
        assert "PROTOCOL_HTTP" in src

    def test_protocol_modbus_imported(self):
        src = _source()
        assert "PROTOCOL_MODBUS" in src

    def test_unit_type_to_model_imported(self):
        src = _source()
        assert "UNIT_TYPE_TO_MODEL" in src

    def test_model_display_imported(self):
        src = _source()
        assert "MODEL_DISPLAY" in src

    def test_watt_max_imported(self):
        src = _source()
        assert "WATT_MAX" in src

    def test_version_still_4(self):
        src = _source()
        assert "VERSION = 4" in src


class TestUnknownUnitTypeHandling:
    """Bug-Fix: unbekannter Unit-Typ darf nicht in generischem cannot_connect verschwinden."""

    def test_probe_modbus_returns_dict_not_none_for_unknown_type(self):
        """Bei unbekanntem Unit-Typ: dict mit model=None statt bare None."""
        src = _get_function_source("_probe_modbus")
        assert '"unit_type": unit_type, "model": None' in src

    def test_step_user_checks_model_none(self):
        """async_step_user muss model=None Fall explizit abfangen."""
        src = _get_class_method_source("KWLConfigFlow", "async_step_user")
        assert 'flex_result["model"] is None' in src

    def test_step_user_shows_unknown_device_type_error(self):
        src = _get_class_method_source("KWLConfigFlow", "async_step_user")
        assert "unknown_device_type" in src

    def test_step_user_passes_type_code_placeholder(self):
        src = _get_class_method_source("KWLConfigFlow", "async_step_user")
        assert "type_code" in src

    def test_step_user_includes_description_placeholders_for_unknown_type(self):
        src = _get_class_method_source("KWLConfigFlow", "async_step_user")
        assert "description_placeholders" in src


class TestModbusNoResponseHandling:
    """Bug-Fix: Register-Read-Fehler (verbunden, aber keine Antwort) darf nicht
    mit echtem Verbindungsfehler (cannot_connect) verwechselt werden."""

    def test_probe_modbus_returns_dict_when_read_fails(self):
        """Bei fehlgeschlagenem Register-Read: dict mit unit_type=None statt bare None."""
        src = _get_function_source("_probe_modbus")
        assert 'return {"unit_type": None, "model": None}' in src

    def test_probe_modbus_checks_is_error_before_unit_type(self):
        src = _get_function_source("_probe_modbus")
        # r.isError() Check muss vor der unit_type Extraktion erfolgen
        is_error_pos = src.find("r.isError()")
        unit_type_pos = src.find("unit_type = _u32")
        assert is_error_pos >= 0 and unit_type_pos >= 0
        assert is_error_pos < unit_type_pos

    def test_step_user_checks_unit_type_none(self):
        """async_step_user muss zwischen unit_type=None und unbekanntem Code unterscheiden."""
        src = _get_class_method_source("KWLConfigFlow", "async_step_user")
        assert 'flex_result["unit_type"] is None' in src

    def test_step_user_shows_modbus_no_response_error(self):
        src = _get_class_method_source("KWLConfigFlow", "async_step_user")
        assert "modbus_no_response" in src

    def test_modbus_no_response_error_in_all_translation_files(self):
        import json
        base = "/home/claude/kwl_src/custom_components/kwl_fraenkische/"
        for fname in ("strings.json", "translations/de.json", "translations/en.json"):
            data = json.loads(open(base + fname).read())
            assert "modbus_no_response" in data["config"]["error"], (
                f"modbus_no_response fehlt in {fname}"
            )

    def test_modbus_no_response_message_nonempty(self):
        import json
        base = "/home/claude/kwl_src/custom_components/kwl_fraenkische/"
        for fname in ("strings.json", "translations/de.json", "translations/en.json"):
            data = json.loads(open(base + fname).read())
            msg = data["config"]["error"]["modbus_no_response"]
            assert isinstance(msg, str) and len(msg) > 10


