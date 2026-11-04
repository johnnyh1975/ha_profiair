"""Tests zu den HACS-Review-Punkten (frenck, PR hacs/default).

- Geräteuhr-Synchronisation ist eine Option und standardmäßig AUS
  (touch: POST /time.htm, flex/flat: Register 40111)
- Options-Flow bietet die Option an, Übersetzungen/README dokumentieren sie
- Release-Zip enthält kein Bytecode; __pycache__ ist nicht im Repository
"""
from __future__ import annotations

import ast
import importlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_CC = _ROOT / "custom_components" / "kwl_fraenkische"


def _const():
    return importlib.import_module("custom_components.kwl_fraenkische.const")


def _flex_mod():
    return importlib.import_module("custom_components.kwl_fraenkische.flex_coordinator")


def _touch_mod():
    return importlib.import_module("custom_components.kwl_fraenkische.coordinator")


def _entry(options):
    return SimpleNamespace(options=options, data={}, entry_id="e1", async_on_unload=MagicMock())


def _flex(options):
    c = _flex_mod().KWLFlexCoordinator.__new__(_flex_mod().KWLFlexCoordinator)
    c.config_entry = _entry(options)
    c.hass = MagicMock()
    c._time_sync_failures = 0
    c._lock = MagicMock()
    c._client = MagicMock(connected=True)
    c._write_uint32 = AsyncMock()
    return c


def _touch(options):
    c = _touch_mod().KWLCoordinator.__new__(_touch_mod().KWLCoordinator)
    c.config_entry = _entry(options)
    c.hass = MagicMock()
    c.host = "192.0.2.1"
    c.capabilities = None
    c._unsub_time_sync = None
    c._get_session = MagicMock()
    return c


class TestOptionConstant:
    def test_default_is_off(self):
        const = _const()
        assert const.CONF_SYNC_TIME == "sync_time"
        assert const.DEFAULT_SYNC_TIME is False


class TestFlexClockSync:
    def test_enabled_property_defaults_to_false(self):
        assert _flex({}).sync_time_enabled is False
        assert _flex({"sync_time": True}).sync_time_enabled is True

    @pytest.mark.asyncio
    async def test_no_write_when_disabled(self):
        c = _flex({})
        await c._async_sync_time()
        c._write_uint32.assert_not_called()

    @pytest.mark.asyncio
    async def test_writes_register_when_enabled(self):
        c = _flex({"sync_time": True})
        c._lock = _AsyncLock()
        await c._async_sync_time()
        c._write_uint32.assert_awaited_once()
        assert c._write_uint32.await_args.args[0] == 110  # 40111

    @pytest.mark.asyncio
    async def test_setup_registers_no_timer_when_disabled(self):
        c = _flex({})
        c._async_sync_time = AsyncMock()
        store = MagicMock()
        store.async_load = AsyncMock(return_value=None)
        with patch.object(_flex_mod(), "Store", return_value=store), patch(
            "homeassistant.helpers.event.async_track_time_interval"
        ) as track:
            await c.async_setup()
        c._async_sync_time.assert_not_called()
        intervals = [call.args[2] for call in track.call_args_list]
        assert _flex_mod().TIME_SYNC_INTERVAL not in intervals

    @pytest.mark.asyncio
    async def test_setup_syncs_and_schedules_when_enabled(self):
        c = _flex({"sync_time": True})
        c._async_sync_time = AsyncMock()
        store = MagicMock()
        store.async_load = AsyncMock(return_value=None)
        with patch.object(_flex_mod(), "Store", return_value=store), patch(
            "homeassistant.helpers.event.async_track_time_interval"
        ) as track:
            await c.async_setup()
        c._async_sync_time.assert_awaited_once()
        intervals = [call.args[2] for call in track.call_args_list]
        assert _flex_mod().TIME_SYNC_INTERVAL in intervals


class _AsyncLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class TestTouchClockSync:
    def test_enabled_property_defaults_to_false(self):
        assert _touch({}).sync_time_enabled is False
        assert _touch({"sync_time": True}).sync_time_enabled is True

    @pytest.mark.asyncio
    async def test_no_post_when_disabled(self):
        c = _touch({})
        await c._async_sync_time()
        c._get_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_setup_registers_no_timer_when_disabled(self):
        c = _touch({})
        c._async_sync_time = AsyncMock()
        store = MagicMock()
        store.async_load = AsyncMock(return_value=None)
        with patch.object(_touch_mod(), "Store", return_value=store), patch.object(
            _touch_mod(), "async_track_time_interval"
        ) as track:
            await c.async_setup()
        c._async_sync_time.assert_not_called()
        assert c._unsub_time_sync is None
        intervals = [call.args[2] for call in track.call_args_list]
        assert _touch_mod().TIME_SYNC_INTERVAL not in intervals

    @pytest.mark.asyncio
    async def test_setup_syncs_and_schedules_when_enabled(self):
        c = _touch({"sync_time": True})
        c._async_sync_time = AsyncMock()
        store = MagicMock()
        store.async_load = AsyncMock(return_value=None)
        with patch.object(_touch_mod(), "Store", return_value=store), patch.object(
            _touch_mod(), "async_track_time_interval"
        ) as track:
            await c.async_setup()
        c._async_sync_time.assert_awaited_once()
        intervals = [call.args[2] for call in track.call_args_list]
        assert _touch_mod().TIME_SYNC_INTERVAL in intervals


class TestOptionsFlowStructure:
    """Der Options-Flow bietet die Option für touch und flex/flat an (nicht für lite)."""

    def _fn(self, name):
        tree = ast.parse((_CC / "config_flow.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return ast.get_source_segment((_CC / "config_flow.py").read_text(encoding="utf-8"), node)
        raise AssertionError(name)

    @pytest.mark.parametrize("fn", ["_touch_schema", "_flex_schema"])
    def test_schema_has_optional_bool_default_off(self, fn):
        src = self._fn(fn)
        assert "CONF_SYNC_TIME" in src and "DEFAULT_SYNC_TIME" in src
        assert "): bool" in src

    def test_lite_schema_has_no_clock_option(self):
        assert "CONF_SYNC_TIME" not in self._fn("_lite_options_schema")


class TestDocumentation:
    @pytest.mark.parametrize("f", ["strings.json", "translations/de.json", "translations/en.json"])
    def test_translations_describe_option(self, f):
        d = json.loads((_CC / f).read_text(encoding="utf-8"))
        step = d["options"]["step"]["init"]
        assert "sync_time" in step["data"]
        assert "sync_time" in step["data_description"]

    def test_installer_menu_does_not_claim_no_control(self):
        for f in ["strings.json", "translations/de.json", "translations/en.json"]:
            d = json.loads((_CC / f).read_text(encoding="utf-8"))
            text = d["config"]["step"]["installer_menu"]["description"]
            low = text.lower()
            assert "keine steuerung" not in low and "no control" not in low
            assert "stufe.cgi" in text and "setup.htm" in text
            label = d["config"]["step"]["installer_menu"]["menu_options"]["skip_installer"].lower()
            assert "lesezugriff" not in label and "read-only" not in label

    def test_readme_documents_clock_option_and_real_write_behaviour(self):
        readme = (_ROOT / "README.md").read_text(encoding="utf-8")
        assert "Set device clock from Home Assistant" in readme
        assert "Off by default" in readme or "**Off by default.**" in readme
        assert "no true read-only mode" in readme
        assert "no fan level or write control" not in readme
        assert "level changes and write controls are disabled" not in readme


class TestPackaging:
    def test_gitignore_excludes_bytecode(self):
        lines = (_ROOT / ".gitignore").read_text(encoding="utf-8").split()
        assert "__pycache__/" in lines

    def test_no_bytecode_tracked_in_git(self):
        if not (_ROOT / ".git").exists():
            pytest.skip("kein Git-Checkout")
        out = subprocess.run(
            ["git", "ls-files"], cwd=_ROOT, capture_output=True, text=True, check=True
        ).stdout.splitlines()
        assert [f for f in out if "__pycache__" in f or f.endswith(".pyc")] == []

    def test_release_workflow_excludes_and_checks_bytecode(self):
        wf = (_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        assert wf.count("-x '*__pycache__*'") >= 2          # beide Zips
        assert "PYTHONDONTWRITEBYTECODE" in wf             # Testlauf schreibt keinen Cache
        assert "Bytecode (__pycache__ / .pyc) found in the zip" in wf  # Prüfschritt
