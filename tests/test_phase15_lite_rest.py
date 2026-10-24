"""Tests für die experimentelle 140/200-lite-Unterstützung (REST/JSON).

Der Client wird gegen einen ECHTEN lokalen aiohttp-Server geprüft, der sich so
verhält, wie die Hersteller-App es erwartet (Statusfelder, Skalierungen,
Body-Format der POSTs). Das beweist die Logik und das Wire-Format -- NICHT, dass
ein reales Gerät genauso antwortet; dafür fehlen noch Hardware-Daten
(siehe docs/lite-rest.md).
"""
from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer

_CC = Path(__file__).resolve().parent.parent / "custom_components" / "kwl_fraenkische"


def _client_mod():
    return importlib.import_module("custom_components.kwl_fraenkische.lite_client")


def _status_payload(**result_overrides):
    """Statusantwort in der Form, die die App-JS verarbeitet."""
    result = {
        "ps": 1, "fn": 1, "wm": 3,
        "ta": 215, "tw": -1, "sp": 220, "spl": 50, "sph": 400,
        "humidity": 480, "airQuality": 230,
        "cm": 0, "kl": 0, "a": [], "ns": 0, "heatingDisabled": 0,
    }
    result.update(result_overrides)
    return {
        "success": True,
        "deviceType": "002",
        "UID": "AABBCCDDEEFF",
        "RESULT": result,
        "setup": {"serial": "IN1234567", "name": "Wohnzimmer"},
        "sw": {"V": "10.0.2"},
        "net": {"ip": "192.168.1.50", "dhcp": 1},
        "time": {"d": 1, "m": 1, "y": 2026, "h": 8, "i": 0},
    }


# ── parse_status ──────────────────────────────────────────────────────────────

class TestParseStatus:
    def test_full_status_scaling(self):
        d = _client_mod().parse_status(_status_payload())
        assert d.powered is True and d.running is True
        assert d.function == "auto"
        assert d.season == "heating"
        assert d.room_temp == 21.5          # ta ÷ 10
        assert d.setpoint == 22.0
        assert (d.setpoint_min, d.setpoint_max) == (5.0, 40.0)
        assert d.humidity == 48             # humidity ÷ 10
        assert d.air_quality_raw == 230
        assert d.air_quality_level == 2     # round(230/100)
        assert d.water_temp is None         # tw < 0 = nicht vorhanden
        assert d.uid == "AABBCCDDEEFF"
        assert d.serial == "IN1234567" and d.name == "Wohnzimmer"
        assert d.firmware == "10.0.2" and d.ip == "192.168.1.50"
        assert d.device_type == "002"

    @pytest.mark.parametrize("fn,name", [(1, "auto"), (2, "night"), (3, "min"), (4, "max")])
    def test_function_codes(self, fn, name):
        assert _client_mod().parse_status(_status_payload(fn=fn)).function == name

    def test_unknown_or_zero_function_is_none(self):
        assert _client_mod().parse_status(_status_payload(fn=0)).function is None
        assert _client_mod().parse_status(_status_payload(fn=9)).function is None

    @pytest.mark.parametrize("wm,season", [(3, "heating"), (5, "cooling"), (7, None)])
    def test_season_codes(self, wm, season):
        assert _client_mod().parse_status(_status_payload(wm=wm)).season == season

    def test_air_quality_level_minimum_is_one(self):
        d = _client_mod().parse_status(_status_payload(airQuality=30))
        assert d.air_quality_level == 1

    def test_air_quality_and_humidity_zero_mean_unavailable(self):
        d = _client_mod().parse_status(_status_payload(airQuality=0, humidity=0))
        assert d.air_quality_raw is None and d.air_quality_level is None
        assert d.humidity is None

    def test_water_temperature_when_present(self):
        assert _client_mod().parse_status(_status_payload(tw=455)).water_temp == 45.5

    def test_power_off(self):
        d = _client_mod().parse_status(_status_payload(ps=0))
        assert d.powered is False and d.running is False

    def test_contact_presence_blocks_running_like_the_app(self):
        d = _client_mod().parse_status(_status_payload(a=["CP"]))
        assert d.powered is True
        assert d.contact_presence is True
        assert d.running is False           # App: active = 0 bei CP
        assert d.has_alarm is False         # CP allein ist kein Störungsalarm

    def test_other_alarms(self):
        d = _client_mod().parse_status(_status_payload(a=["CP", "E1"]))
        assert d.alarms == ("CP", "E1") and d.has_alarm is True

    def test_flags(self):
        d = _client_mod().parse_status(_status_payload(cm=1, kl=1, ns=1, heatingDisabled=1))
        assert d.calendar_active and d.key_lock and d.standalone and d.heating_disabled

    def test_missing_optional_fields_are_tolerated(self):
        payload = {"success": True, "RESULT": {"ps": 1}}
        d = _client_mod().parse_status(payload)
        assert d.powered is True
        assert d.function is None and d.room_temp is None and d.uid is None
        assert d.device_type == ""

    def test_string_numbers_are_accepted(self):
        d = _client_mod().parse_status(_status_payload(ta="215", fn="2"))
        assert d.room_temp == 21.5 and d.function == "night"

    def test_non_finite_and_garbage_numbers_are_ignored(self):
        d = _client_mod().parse_status(_status_payload(ta="nan", fn="inf", sp="abc", humidity=True))
        assert d.room_temp is None and d.function is None and d.setpoint is None
        assert d.humidity is None

    def test_password_fields_are_masked_in_raw_result(self):
        """innova-controls maskiert RESULT["pwd"]; wir tun es ebenfalls."""
        d = _client_mod().parse_status(_status_payload(pwd="geheim", wifiPassword="x", other=1))
        assert d.result["pwd"] == "__OBFUSCATED__"
        assert d.result["wifiPassword"] == "__OBFUSCATED__"
        assert d.result["other"] == 1
        assert "geheim" not in repr(d) and "geheim" not in json.dumps(d.result)

    def test_result_is_kept_raw(self):
        d = _client_mod().parse_status(_status_payload(extra_field=7))
        assert d.result["extra_field"] == 7

    @pytest.mark.parametrize("payload", [None, [], "x", 5])
    def test_non_object_is_rejected(self, payload):
        with pytest.raises(_client_mod().LiteResponseError):
            _client_mod().parse_status(payload)

    def test_success_false_carries_error_code(self):
        with pytest.raises(_client_mod().LiteResponseError) as exc:
            _client_mod().parse_status({"success": False, "error": "E012"})
        assert exc.value.error_code == "E012"

    def test_missing_result_is_rejected(self):
        with pytest.raises(_client_mod().LiteResponseError):
            _client_mod().parse_status({"success": True, "deviceType": "002"})

    def test_other_device_family_is_rejected(self):
        with pytest.raises(_client_mod().LiteUnsupportedDevice):
            _client_mod().parse_status({**_status_payload(), "deviceType": "001"})

    def test_empty_device_type_is_accepted_like_the_app(self):
        assert _client_mod().parse_status({**_status_payload(), "deviceType": ""}).device_type == ""


# ── Client gegen echten Mock-Server ───────────────────────────────────────────

class _MockDevice:
    """Minimaler Nachbau des Geräteverhaltens, so wie die App es voraussetzt."""

    def __init__(self) -> None:
        self.state = _status_payload()
        self.requests: list[tuple[str, str, str, str]] = []  # method, path, ctype, body
        self.fail_status: int | None = None
        self.reject_with_error: str | None = None
        self.raw_body: str | None = None

    async def handle(self, request: web.Request) -> web.Response:
        body = (await request.read()).decode()
        self.requests.append(
            (request.method, request.path, request.headers.get("Content-Type", ""), body)
        )
        if self.fail_status:
            return web.Response(status=self.fail_status)
        if self.raw_body is not None:
            return web.Response(text=self.raw_body, content_type="text/html")
        path = request.path.removeprefix("/api/v/1/")
        result = self.state["RESULT"]
        if self.reject_with_error and request.method == "POST":
            return web.json_response({"success": False, "error": self.reject_with_error})
        if request.method == "GET" and path == "status":
            return web.json_response(self.state)
        if request.method == "POST" and path in ("power/on", "power/off"):
            result["ps"] = 1 if path.endswith("on") else 0
            return web.json_response({"success": True})
        if request.method == "POST" and path.startswith("set/function/"):
            result["fn"] = {"auto": 1, "night": 2, "min": 3, "max": 4}[path.rsplit("/", 1)[1]]
            return web.json_response({"success": True})
        if request.method == "POST" and path == "set/setpoint":
            result["sp"] = json.loads(body)["temp"]
            return web.json_response({"success": True})
        if request.method == "POST" and path in ("set/mode/heating", "set/mode/cooling"):
            result["wm"] = 3 if path.endswith("heating") else 5
            return web.json_response({"success": True})
        if request.method == "POST" and path in ("set/lock/on", "set/lock/off"):
            result["kl"] = 1 if path.endswith("on") else 0
            return web.json_response({"success": True})
        return web.json_response({"success": False, "error": "E012"})


@pytest_asyncio.fixture
async def device():
    mock = _MockDevice()
    app = web.Application()
    app.router.add_route("*", "/api/v/1/{tail:.*}", mock.handle)
    server = TestServer(app)
    await server.start_server()
    async with aiohttp.ClientSession() as session:
        mock.client = _client_mod().KWLLiteClient(
            session, f"{server.host}:{server.port}", timeout=2
        )
        mock.session = session
        mock.hostport = f"{server.host}:{server.port}"
        yield mock
    await server.close()


class TestClientWire:
    @pytest.mark.asyncio
    async def test_get_status_decodes(self, device):
        d = await device.client.get_status()
        assert d.room_temp == 21.5 and d.function == "auto"
        assert device.requests[0][:2] == ("GET", "/api/v/1/status")

    @pytest.mark.asyncio
    async def test_set_function_wire_format_matches_app(self, device):
        await device.client.async_set_function("night")
        method, path, ctype, body = device.requests[-1]
        assert (method, path) == ("POST", "/api/v/1/set/function/night")
        # App: JSON-String als Body, Content-Type form-urlencoded
        assert ctype.startswith("application/x-www-form-urlencoded")
        assert json.loads(body) == {"value": 1}
        assert (await device.client.get_status()).function == "night"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("fn", ["auto", "night", "min", "max"])
    async def test_all_functions_roundtrip(self, device, fn):
        await device.client.async_set_function(fn)
        assert (await device.client.get_status()).function == fn

    @pytest.mark.asyncio
    async def test_power_roundtrip_has_no_body(self, device):
        await device.client.async_set_power(False)
        assert device.requests[-1][:2] == ("POST", "/api/v/1/power/off")
        assert device.requests[-1][3] == ""
        assert (await device.client.get_status()).powered is False
        await device.client.async_set_power(True)
        assert (await device.client.get_status()).powered is True

    @pytest.mark.asyncio
    async def test_unknown_function_raises_before_any_request(self, device):
        with pytest.raises(ValueError):
            await device.client.async_set_function("turbo")
        assert device.requests == []

    @pytest.mark.asyncio
    async def test_http_error_is_connection_error(self, device):
        device.fail_status = 500
        with pytest.raises(_client_mod().LiteConnectionError):
            await device.client.get_status()

    @pytest.mark.asyncio
    async def test_non_json_is_response_error(self, device):
        device.raw_body = "<html>nope</html>"
        with pytest.raises(_client_mod().LiteResponseError):
            await device.client.get_status()

    @pytest.mark.asyncio
    async def test_json_with_html_content_type_is_accepted(self, device):
        """ESP-Webserver setzen den Content-Type nicht immer auf application/json."""
        device.raw_body = json.dumps(_status_payload())
        assert (await device.client.get_status()).function == "auto"

    @pytest.mark.asyncio
    async def test_rejected_write_raises_with_code(self, device):
        device.reject_with_error = "E012"
        with pytest.raises(_client_mod().LiteResponseError) as exc:
            await device.client.async_set_power(True)
        assert exc.value.error_code == "E012"

    @pytest.mark.asyncio
    async def test_unreachable_host_is_connection_error(self):
        async with aiohttp.ClientSession() as session:
            client = _client_mod().KWLLiteClient(session, "127.0.0.1:9", timeout=1)
            with pytest.raises(_client_mod().LiteConnectionError):
                await client.get_status()

    @pytest.mark.asyncio
    async def test_setpoint_wire_format_is_integer_tenths(self, device):
        await device.client.async_set_setpoint(22.5)
        method, path, ctype, body = device.requests[-1]
        assert (method, path) == ("POST", "/api/v/1/set/setpoint")
        assert ctype.startswith("application/x-www-form-urlencoded")
        assert json.loads(body) == {"temp": 225}
        assert isinstance(json.loads(body)["temp"], int)
        assert (await device.client.get_status()).setpoint == 22.5

    @pytest.mark.asyncio
    @pytest.mark.parametrize("value", [4.9, 40.5, -1, 100])
    async def test_setpoint_out_of_range_rejected_before_request(self, device, value):
        with pytest.raises(ValueError):
            await device.client.async_set_setpoint(value)
        assert device.requests == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("value,tenths", [(5.0, 50), (40.0, 400), (21.3, 213)])
    async def test_setpoint_rounding_and_bounds(self, device, value, tenths):
        await device.client.async_set_setpoint(value)
        assert json.loads(device.requests[-1][3]) == {"temp": tenths}

    @pytest.mark.asyncio
    async def test_season_roundtrip_without_body(self, device):
        await device.client.async_set_season("cooling")
        assert device.requests[-1][:2] == ("POST", "/api/v/1/set/mode/cooling")
        assert device.requests[-1][3] == ""
        assert (await device.client.get_status()).season == "cooling"
        await device.client.async_set_season("heating")
        assert (await device.client.get_status()).season == "heating"

    @pytest.mark.asyncio
    async def test_unknown_season_rejected(self, device):
        with pytest.raises(ValueError):
            await device.client.async_set_season("auto")
        assert device.requests == []

    @pytest.mark.asyncio
    async def test_key_lock_roundtrip(self, device):
        await device.client.async_set_key_lock(True)
        assert device.requests[-1][:2] == ("POST", "/api/v/1/set/lock/on")
        assert (await device.client.get_status()).key_lock is True
        await device.client.async_set_key_lock(False)
        assert (await device.client.get_status()).key_lock is False

    def test_client_exposes_only_the_harmless_writes(self):
        """Absicherung: keine Schreibmethode für rs485/setup/network (könnten
        Geräteregister oder Netzwerkkonfiguration zerstören)."""
        writers = {
            n for n in dir(_client_mod().KWLLiteClient)
            if n.startswith("async_")
        }
        assert writers == {
            "async_set_power", "async_set_function", "async_set_setpoint",
            "async_set_season", "async_set_key_lock",
        }

    def test_dangerous_endpoints_are_not_requested_anywhere_in_code(self):
        for path in _CC.glob("lite_*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if node.value.startswith(("rs485/", "network/")) and "\n" not in node.value:
                        pytest.fail(f"{path.name}: verdächtiger Pfad {node.value!r}")


# ── Config-Flow-Probe ─────────────────────────────────────────────────────────

class TestProbeLite:
    @pytest.mark.asyncio
    async def test_detects_lite_device(self, device):
        cf = importlib.import_module("custom_components.kwl_fraenkische.config_flow")
        data = await cf._probe_lite(device.hostport)
        assert data is not None and data.serial == "IN1234567"

    @pytest.mark.asyncio
    async def test_non_lite_answer_is_none(self, device):
        cf = importlib.import_module("custom_components.kwl_fraenkische.config_flow")
        device.raw_body = "<status><config_mac>x</config_mac></status>"
        assert await cf._probe_lite(device.hostport) is None

    @pytest.mark.asyncio
    async def test_other_device_type_is_none(self, device):
        cf = importlib.import_module("custom_components.kwl_fraenkische.config_flow")
        device.state["deviceType"] = "007"
        assert await cf._probe_lite(device.hostport) is None

    @pytest.mark.asyncio
    async def test_unreachable_is_none_and_never_raises(self):
        cf = importlib.import_module("custom_components.kwl_fraenkische.config_flow")
        assert await cf._probe_lite("127.0.0.1:9") is None


# ── Config-Flow ───────────────────────────────────────────────────────────────
# Die HA-Basisklassen sind in conftest.py gestubbt (MagicMock-artig), daher
# werden Flow-Klassen -- wie in den übrigen Config-Flow-Tests -- per AST geprüft;
# die Logik selbst steckt in reinen Modulfunktionen, die direkt getestet werden.

def _cf():
    return importlib.import_module("custom_components.kwl_fraenkische.config_flow")


def _method_calls_in_order(class_name: str, method: str) -> list[str]:
    tree = ast.parse((_CC / "config_flow.py").read_text(encoding="utf-8"))
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name):
        for fn in cls.body:
            if isinstance(fn, ast.AsyncFunctionDef) and fn.name == method:
                names = []
                for node in ast.walk(fn):
                    if isinstance(node, ast.Call):
                        f = node.func
                        names.append(f.id if isinstance(f, ast.Name) else getattr(f, "attr", ""))
                return names
    raise AssertionError(f"{class_name}.{method} nicht gefunden")


class TestConfigFlow:
    def test_probe_order_touch_then_lite_then_modbus(self):
        src = (_CC / "config_flow.py").read_text(encoding="utf-8")
        user = src[src.index("async def async_step_user"):src.index("async def async_step_installer_menu")]
        touch, lite, modbus = (user.index(n) for n in ("_fetch_device_info(", "_probe_lite(", "_probe_modbus("))
        assert touch < lite < modbus

    def test_user_step_routes_to_confirm_lite(self):
        assert "async_step_confirm_lite" in _method_calls_in_order("KWLConfigFlow", "async_step_user")

    def test_unique_id_prefers_uid_then_serial_then_host(self):
        cm = _client_mod()
        full = cm.parse_status(_status_payload())
        assert _cf()._lite_unique_id("h", full) == "AABBCCDDEEFF"
        no_uid = _status_payload()
        del no_uid["UID"]
        assert _cf()._lite_unique_id("h", cm.parse_status(no_uid)) == "IN1234567"
        del no_uid["setup"]
        assert _cf()._lite_unique_id("h", cm.parse_status(no_uid)) == "h"

    def test_entry_data(self):
        lite = _client_mod().parse_status(_status_payload())
        data = _cf()._lite_entry_data("10.0.0.9", lite, "AABBCCDDEEFF")
        assert data == {
            "host": "10.0.0.9", "protocol": "rest", "mac": "AABBCCDDEEFF",
            "model": "profi_air_lite", "firmware": "10.0.2",
            "serial": "IN1234567", "name": "Wohnzimmer",
        }

    def test_confirm_step_uses_helpers(self):
        calls = _method_calls_in_order("KWLConfigFlow", "async_step_confirm_lite")
        assert {"_lite_unique_id", "_lite_entry_data", "async_set_unique_id",
                "_abort_if_unique_id_configured", "async_create_entry"} <= set(calls)

    def test_options_schema_enforces_lite_minimum_interval(self):
        schema = _cf()._lite_options_schema({})
        assert schema({"scan_interval": 15})["scan_interval"] == 15
        with pytest.raises(Exception):
            schema({"scan_interval": 5})
        assert schema({})["scan_interval"] == 30

    def test_options_flow_routes_rest_to_lite_schema(self):
        calls = _method_calls_in_order("KWLOptionsFlow", "async_step_init")
        assert "_lite_options_schema" in calls


# ── Coordinator ───────────────────────────────────────────────────────────────

def _coordinator(client):
    mod = importlib.import_module("custom_components.kwl_fraenkische.lite_coordinator")
    c = mod.KWLLiteCoordinator.__new__(mod.KWLLiteCoordinator)
    c._host = "10.0.0.5"
    c.client = client
    c.device_info = {"sw_version": "1.0"}
    c.async_request_refresh = AsyncMock()
    return c


class TestCoordinator:
    @pytest.mark.asyncio
    async def test_update_returns_parsed_data(self):
        cm = _client_mod()
        data = cm.parse_status(_status_payload())
        client = MagicMock(get_status=AsyncMock(return_value=data))
        c = _coordinator(client)
        assert await c._async_update_data() is data
        assert c.device_info["sw_version"] == "10.0.2"   # Firmware nachgeführt

    @pytest.mark.asyncio
    @pytest.mark.parametrize("err_name", ["LiteConnectionError", "LiteResponseError", "LiteUnsupportedDevice"])
    async def test_client_errors_become_update_failed(self, err_name):
        cm = _client_mod()
        from homeassistant.helpers.update_coordinator import UpdateFailed
        client = MagicMock(get_status=AsyncMock(side_effect=getattr(cm, err_name)("x")))
        with pytest.raises(UpdateFailed):
            await _coordinator(client)._async_update_data()

    @pytest.mark.asyncio
    async def test_write_refreshes(self):
        client = MagicMock(async_set_function=AsyncMock(), async_set_power=AsyncMock())
        c = _coordinator(client)
        await c.async_set_function("max")
        await c.async_set_power(False)
        client.async_set_function.assert_awaited_once_with("max")
        client.async_set_power.assert_awaited_once_with(False)
        assert c.async_request_refresh.await_count == 2

    @pytest.mark.asyncio
    async def test_write_error_becomes_homeassistant_error_without_refresh(self):
        from homeassistant.exceptions import HomeAssistantError
        cm = _client_mod()
        client = MagicMock(async_set_power=AsyncMock(side_effect=cm.LiteConnectionError("weg")))
        c = _coordinator(client)
        with pytest.raises(HomeAssistantError):
            await c.async_set_power(True)
        c.async_request_refresh.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_season_powers_on_first_when_device_is_off(self):
        cm = _client_mod()
        client = MagicMock(async_set_power=AsyncMock(), async_set_season=AsyncMock())
        order = []
        client.async_set_power.side_effect = lambda on: order.append(("power", on))
        client.async_set_season.side_effect = lambda s: order.append(("season", s))
        c = _coordinator(client)
        c.data = cm.parse_status(_status_payload(ps=0))
        await c.async_set_season("cooling")
        assert order == [("power", True), ("season", "cooling")]

    @pytest.mark.asyncio
    async def test_season_does_not_power_on_when_already_on(self):
        cm = _client_mod()
        client = MagicMock(async_set_power=AsyncMock(), async_set_season=AsyncMock())
        c = _coordinator(client)
        c.data = cm.parse_status(_status_payload(ps=1))
        await c.async_set_season("heating")
        client.async_set_power.assert_not_awaited()
        client.async_set_season.assert_awaited_once_with("heating")

    @pytest.mark.asyncio
    async def test_setpoint_and_key_lock_write_and_refresh(self):
        client = MagicMock(async_set_setpoint=AsyncMock(), async_set_key_lock=AsyncMock())
        c = _coordinator(client)
        await c.async_set_setpoint(21.5)
        await c.async_set_key_lock(True)
        client.async_set_setpoint.assert_awaited_once_with(21.5)
        client.async_set_key_lock.assert_awaited_once_with(True)
        assert c.async_request_refresh.await_count == 2

    def test_scan_interval_is_clamped_in_source(self):
        src = (_CC / "lite_coordinator.py").read_text(encoding="utf-8")
        assert "max(" in src and "LITE_MIN_SCAN_INTERVAL" in src


# ── Entitäten ─────────────────────────────────────────────────────────────────

def _lite_coordinator_with(data, last_update_success=True):
    c = MagicMock()
    c.data = data
    c.last_update_success = last_update_success
    c.model_slug = "profi_air_lite"
    c.unique_prefix = "AABBCCDDEEFF"
    c.device_info = {"identifiers": {("kwl_fraenkische", "e1")}}
    c.async_set_power = AsyncMock()
    c.async_set_function = AsyncMock()
    return c


def _ent():
    return importlib.import_module("custom_components.kwl_fraenkische.lite_entities")


class TestEntities:
    def test_fan_state(self):
        data = _client_mod().parse_status(_status_payload(fn=2))
        fan = _ent().KWLLiteFan(_lite_coordinator_with(data))
        assert fan.is_on is True and fan.preset_mode == "night"
        assert fan.available is True
        assert fan.extra_state_attributes["contact_presence"] is False

    def test_fan_off_when_window_contact_active(self):
        data = _client_mod().parse_status(_status_payload(a=["CP"]))
        fan = _ent().KWLLiteFan(_lite_coordinator_with(data))
        assert fan.is_on is False
        assert fan.extra_state_attributes["contact_presence"] is True

    def test_fan_unavailable_without_data(self):
        fan = _ent().KWLLiteFan(_lite_coordinator_with(None))
        assert fan.available is False and fan.is_on is None and fan.preset_mode is None

    def test_fan_unavailable_after_failed_update(self):
        data = _client_mod().parse_status(_status_payload())
        fan = _ent().KWLLiteFan(_lite_coordinator_with(data, last_update_success=False))
        assert fan.available is False

    def test_fan_identity(self):
        fan = _ent().KWLLiteFan(_lite_coordinator_with(None))
        assert fan._attr_unique_id == "AABBCCDDEEFF_fan"
        assert fan.entity_id == "fan.profi_air_lite"
        assert fan._attr_preset_modes == ["auto", "night", "min", "max"]

    @pytest.mark.asyncio
    async def test_fan_commands(self):
        coord = _lite_coordinator_with(_client_mod().parse_status(_status_payload()))
        fan = _ent().KWLLiteFan(coord)
        await fan.async_set_preset_mode("max")
        coord.async_set_function.assert_awaited_once_with("max")
        await fan.async_set_preset_mode("turbo")           # ungültig: ignoriert
        assert coord.async_set_function.await_count == 1
        await fan.async_turn_off()
        coord.async_set_power.assert_awaited_with(False)
        await fan.async_turn_on(preset_mode="min")
        coord.async_set_power.assert_awaited_with(True)
        coord.async_set_function.assert_awaited_with("min")

    @pytest.mark.asyncio
    async def test_turn_on_without_preset_does_not_change_function(self):
        coord = _lite_coordinator_with(_client_mod().parse_status(_status_payload()))
        await _ent().KWLLiteFan(coord).async_turn_on()
        coord.async_set_power.assert_awaited_once_with(True)
        coord.async_set_function.assert_not_awaited()

    def test_sensor_values(self):
        data = _client_mod().parse_status(_status_payload(a=["E1"], tw=300))
        coord = _lite_coordinator_with(data)
        values = {
            d.key: _ent().KWLLiteSensor(coord, d).native_value
            for d in _ent().LITE_SENSORS
        }
        assert values == {
            "room_temperature": 21.5, "humidity": 48, "air_quality": 2,
            "water_temperature": 30.0, "alarms": "E1",
        }

    def test_sensor_value_none_without_data(self):
        coord = _lite_coordinator_with(None)
        assert all(
            _ent().KWLLiteSensor(coord, d).native_value is None for d in _ent().LITE_SENSORS
        )

    def test_binary_sensor_values(self):
        data = _client_mod().parse_status(_status_payload(a=["CP"], kl=1))
        coord = _lite_coordinator_with(data)
        values = {
            d.key: _ent().KWLLiteBinarySensor(coord, d).is_on
            for d in _ent().LITE_BINARY_SENSORS
        }
        assert values == {"alarm_active": False, "contact_presence": True}

    def test_setpoint_entity(self):
        data = _client_mod().parse_status(_status_payload(sp=225, spl=100, sph=300))
        sp = _ent().KWLLiteSetpoint(_lite_coordinator_with(data))
        assert sp.native_value == 22.5
        assert (sp.native_min_value, sp.native_max_value) == (10.0, 30.0)
        assert sp._attr_native_step == 0.5
        assert sp._attr_entity_registry_enabled_default is False

    def test_setpoint_limits_never_exceed_client_bounds_or_default_without_data(self):
        wide = _client_mod().parse_status(_status_payload(spl=0, sph=900))
        sp = _ent().KWLLiteSetpoint(_lite_coordinator_with(wide))
        assert (sp.native_min_value, sp.native_max_value) == (5.0, 40.0)
        none = _ent().KWLLiteSetpoint(_lite_coordinator_with(None))
        assert (none.native_min_value, none.native_max_value) == (5.0, 40.0)
        assert none.native_value is None

    @pytest.mark.asyncio
    async def test_setpoint_command(self):
        coord = _lite_coordinator_with(None)
        coord.async_set_setpoint = AsyncMock()
        await _ent().KWLLiteSetpoint(coord).async_set_native_value(21.0)
        coord.async_set_setpoint.assert_awaited_once_with(21.0)

    def test_season_entity(self):
        data = _client_mod().parse_status(_status_payload(wm=5))
        sel = _ent().KWLLiteSeason(_lite_coordinator_with(data))
        assert sel.current_option == "cooling"
        assert sel._attr_options == ["heating", "cooling"]
        assert sel._attr_entity_registry_enabled_default is False
        assert _ent().KWLLiteSeason(_lite_coordinator_with(None)).current_option is None

    @pytest.mark.asyncio
    async def test_season_command_ignores_unknown_option(self):
        coord = _lite_coordinator_with(None)
        coord.async_set_season = AsyncMock()
        sel = _ent().KWLLiteSeason(coord)
        await sel.async_select_option("heating")
        await sel.async_select_option("auto")
        coord.async_set_season.assert_awaited_once_with("heating")

    @pytest.mark.asyncio
    async def test_key_lock_switch(self):
        coord = _lite_coordinator_with(_client_mod().parse_status(_status_payload(kl=1)))
        coord.async_set_key_lock = AsyncMock()
        sw = _ent().KWLLiteKeyLock(coord)
        assert sw.is_on is True
        await sw.async_turn_off()
        coord.async_set_key_lock.assert_awaited_with(False)
        await sw.async_turn_on()
        coord.async_set_key_lock.assert_awaited_with(True)
        assert _ent().KWLLiteKeyLock(_lite_coordinator_with(None)).is_on is None

    def test_unique_ids_are_unique(self):
        coord = _lite_coordinator_with(None)
        ids = [_ent().KWLLiteFan(coord)._attr_unique_id,
               _ent().KWLLiteSetpoint(coord)._attr_unique_id,
               _ent().KWLLiteSeason(coord)._attr_unique_id,
               _ent().KWLLiteKeyLock(coord)._attr_unique_id]
        ids += [_ent().KWLLiteSensor(coord, d)._attr_unique_id for d in _ent().LITE_SENSORS]
        ids += [_ent().KWLLiteBinarySensor(coord, d)._attr_unique_id for d in _ent().LITE_BINARY_SENSORS]
        assert len(ids) == len(set(ids))


# ── Verdrahtung ───────────────────────────────────────────────────────────────

class TestWiring:
    def test_lite_platforms(self):
        init = importlib.import_module("custom_components.kwl_fraenkische")
        assert [str(p) for p in init.PLATFORMS_LITE] == [
            "fan", "sensor", "binary_sensor", "number", "select", "switch",
        ]

    def test_switch_platform_is_only_forwarded_for_lite(self):
        init = importlib.import_module("custom_components.kwl_fraenkische")
        assert "switch" not in [str(p) for p in init.PLATFORMS]
        assert (_CC / "switch.py").exists()

    def test_platforms_for_selects_by_protocol(self):
        init = importlib.import_module("custom_components.kwl_fraenkische")
        rest = MagicMock(data={"protocol": "rest"})
        modbus = MagicMock(data={"protocol": "modbus"})
        legacy = MagicMock(data={})
        assert init._platforms_for(rest) is init.PLATFORMS_LITE
        assert init._platforms_for(modbus) is init.PLATFORMS
        assert init._platforms_for(legacy) is init.PLATFORMS

    def test_setup_and_unload_use_the_same_platform_selection(self):
        src = (_CC / "__init__.py").read_text(encoding="utf-8")
        assert src.count("_platforms_for(entry)") == 2

    def test_existing_platform_list_is_unchanged(self):
        init = importlib.import_module("custom_components.kwl_fraenkische")
        assert [str(p) for p in init.PLATFORMS] == [
            "fan", "sensor", "binary_sensor", "number", "select", "button",
        ]

    def test_rest_protocol_constant(self):
        const = importlib.import_module("custom_components.kwl_fraenkische.const")
        assert const.PROTOCOL_REST == "rest"
        # Bewusst nicht in den Tabellen der Lüfter-Modelle:
        assert const.MODEL_PROFI_AIR_LITE not in const.MODEL_PROTOCOLS
        assert const.MODEL_PROFI_AIR_LITE not in const.WATT_DEFAULTS

    def test_translation_keys_used_by_lite_entities_exist(self):
        strings = json.loads((_CC / "strings.json").read_text(encoding="utf-8"))
        ent = _ent()
        for d in ent.LITE_SENSORS:
            assert d.translation_key in strings["entity"]["sensor"], d.key
        for d in ent.LITE_BINARY_SENSORS:
            assert d.translation_key in strings["entity"]["binary_sensor"], d.key
        fan = strings["entity"]["fan"]["lite_fan"]
        assert set(fan["state_attributes"]["preset_mode"]["state"]) == set(ent.FUNCTION_NAMES)
        assert "confirm_lite" in strings["config"]["step"]
        assert "lite_setpoint" in strings["entity"]["number"]
        assert set(strings["entity"]["select"]["lite_season"]["state"]) == set(ent.SEASON_NAMES)
        assert "lite_key_lock" in strings["entity"]["switch"]

    def test_diagnostics_has_lite_branch_without_watt_map(self):
        diag = importlib.import_module("custom_components.kwl_fraenkische.diagnostics")
        entry = MagicMock(
            data={"protocol": "rest", "host": "h", "mac": "m", "serial": "s", "name": "n"},
            options={},
        )
        coord = MagicMock(last_update_success=True, update_interval=None)
        coord.data = _client_mod().parse_status(_status_payload())
        out = diag._lite_diagnostics(entry, coord, {"mac": "**REDACTED**"})
        assert out["experimental"] is True
        assert out["device_data"]["raw_result"]["ta"] == 215
        assert "watt_map" not in out["options"]
        # Identifizierende Felder dürfen nicht in den Diagnosedaten stehen:
        text = json.dumps(out)
        assert "IN1234567" not in text and "AABBCCDDEEFF" not in text
