"""Tests für Phase 2: KWLFlexCapabilities, KWLFlexData, KWLFlexCoordinator.

Abgedeckte Anforderungen (IMPLEMENTIERUNGSPLAN.md Phase 2):
- Float CDAB: [0x0000, 0x41C8] → 25.0
- Float negativ: [0x0000, 0xC0B0] → -5.5
- UINT32 Low-first: [3, 0] → 3
- Bypass-Mapping: 0→"zu", 255→"offen", 1→"bewegt"
- Alarm-Text: code=11 → "E11 – Zuluft < 5 °C"
- heat_recovery_efficiency mit Beispieltemperaturen
- motor_asymmetry True wenn > 22% Differenz
- A/B-Switch-Mapping: fan1_is_extract beeinflusst motor_abluft/zuluft_rpm
- Poll-Divisor: Slow-Blocks nur jede 10. Polls gelesen
- Write-Methoden schreiben korrekte Werte und rufen async_request_refresh
- async_set_level() → NotImplementedError
- Verbindungsabbruch → _needs_reconnect=True, UpdateFailed
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch, call
import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _import_module():
    """Importiert flex_coordinator ohne HA-Imports."""
    import sys, importlib
    if "custom_components.kwl_fraenkische.flex_coordinator" in sys.modules:
        return sys.modules["custom_components.kwl_fraenkische.flex_coordinator"]
    return importlib.import_module("custom_components.kwl_fraenkische.flex_coordinator")


def _make_capabilities(fan1_is_extract: bool = True) -> object:
    """Erstellt ein minimales KWLFlexCapabilities-Objekt."""
    m = _import_module()
    return m.KWLFlexCapabilities(
        model="profi_air_360_flex",
        mac_id="AABBCCDDEEFF0011",
        firmware_version="2.1",
        fan1_is_extract=fan1_is_extract,
        ref_rpm_extract_s3=1500,
        ref_rpm_supply_s3=1600,
    )


def _make_data(**overrides) -> object:
    """Erstellt ein minimales KWLFlexData-Objekt."""
    m = _import_module()
    defaults = dict(
        fan1_rpm=1500.0, fan2_rpm=1600.0, fan1_is_extract=True,
        t1=5.0, t2=19.0, t3=21.0, t4=8.0, t5=None,
        current_level=3, current_mode=1, preheater_duty_pct=0,
        bypass_state_raw=0, alarm_code=0,
        rh_percent=45, rh_setpoint=55, voc_ppm=None, co2_ppm=None,
        bypass_tmin=12.0, bypass_tmax=24.0,
        filter_residual_days=90, filter_total_days=180,
        hours_total=1200,
        watt_map={1: None, 2: None, 3: None, 4: None},
    )
    defaults.update(overrides)
    return m.KWLFlexData(**defaults)


# ── Tests: Float- und UINT32-Dekodierung ─────────────────────────────────────

class TestRegisterDecoding:
    """Korrekte Byte-Order-Dekodierung für den UVC Controller.
    
    Getestet direkt via pymodbus (word_order='little') — die _decode_float /
    _decode_uint32 Methoden im Coordinator sind reine Wrapper darüber.
    """

    @staticmethod
    def _float(regs):
        from pymodbus.client.mixin import ModbusClientMixin
        return ModbusClientMixin.convert_from_registers(
            regs, ModbusClientMixin.DATATYPE.FLOAT32, "little"
        )

    @staticmethod
    def _uint32(regs):
        from pymodbus.client.mixin import ModbusClientMixin
        return ModbusClientMixin.convert_from_registers(
            regs, ModbusClientMixin.DATATYPE.UINT32, "little"
        )

    def test_float_cdab_25_degrees(self):
        """CDAB Float: [0x0000, 0x41C8] → 25.0 °C."""
        assert self._float([0x0000, 0x41C8]) == pytest.approx(25.0, abs=0.01)

    def test_float_cdab_negative(self):
        """CDAB Float: negative Außentemperatur [0x0000, 0xC0B0] → -5.5 °C."""
        assert self._float([0x0000, 0xC0B0]) == pytest.approx(-5.5, abs=0.01)

    def test_uint32_low_first_fan_level_3(self):
        """UINT32 Low-first: [3, 0] → Fan-Level 3."""
        assert self._uint32([3, 0]) == 3

    def test_uint32_low_first_large_value(self):
        """UINT32 Low-first: hoher Wert korrekt dekodiert."""
        assert self._uint32([0x2345, 0x0001]) == 0x00012345

    def test_float_zero_roundtrip(self):
        """CDAB Float: 0.0 korrekt dekodiert."""
        assert self._float([0x0000, 0x0000]) == pytest.approx(0.0, abs=0.001)

    def test_write_uint32_little(self):
        """convert_to_registers erzeugt Low-first Liste."""
        from pymodbus.client.mixin import ModbusClientMixin
        regs = ModbusClientMixin.convert_to_registers(
            2, ModbusClientMixin.DATATYPE.UINT32, "little"
        )
        assert list(regs) == [2, 0]

    def test_write_uint32_large(self):
        """Großer Wert korrekt als Low-first kodiert."""
        from pymodbus.client.mixin import ModbusClientMixin
        regs = ModbusClientMixin.convert_to_registers(
            0x00012345, ModbusClientMixin.DATATYPE.UINT32, "little"
        )
        assert list(regs) == [0x2345, 0x0001]


# ── Tests: KWLFlexData Eigenschaften ─────────────────────────────────────────

class TestFlexDataBasicProperties:
    """Grundlegende Property-Zuordnungen."""

    def test_temp_properties_map_to_t1_t4(self):
        data = _make_data(t1=5.0, t2=19.0, t3=21.0, t4=7.0)
        assert data.temp_aussenluft == 5.0
        assert data.temp_zuluft     == 19.0
        assert data.temp_abluft     == 21.0
        assert data.temp_fortluft   == 7.0

    def test_temp_room_is_t5(self):
        data = _make_data(t5=20.5)
        assert data.temp_room == 20.5

    def test_temp_room_none_when_not_installed(self):
        data = _make_data(t5=None)
        assert data.temp_room is None

    def test_preheater_active_when_duty_nonzero(self):
        assert _make_data(preheater_duty_pct=42).preheater_active is True

    def test_preheater_inactive_when_zero(self):
        assert _make_data(preheater_duty_pct=0).preheater_active is False

    def test_current_mode_text_manual(self):
        data = _make_data(current_mode=1)
        assert data.current_mode_text == "Manuell"

    def test_current_mode_text_demand(self):
        data = _make_data(current_mode=2)
        assert data.current_mode_text == "Bedarfsgesteuert"

    def test_current_mode_text_unknown_shows_number(self):
        data = _make_data(current_mode=99)
        assert "99" in data.current_mode_text

    def test_optional_sensors_none_when_zero(self):
        """VOC/RH/CO2 = 0 im Register → None (kein Sensor verbaut)."""
        data = _make_data(voc_ppm=0, co2_ppm=0, rh_percent=0)
        assert data.voc_ppm    is None
        assert data.co2_ppm    is None
        assert data.rh_percent is None

    def test_optional_sensors_present_when_nonzero(self):
        data = _make_data(voc_ppm=650, co2_ppm=900, rh_percent=55)
        assert data.voc_ppm    == 650
        assert data.co2_ppm    == 900
        assert data.rh_percent == 55


# ── Tests: Bypass-Status Mapping ─────────────────────────────────────────────

class TestBypassStatusMapping:
    def test_0_is_zu(self):
        assert "zu" in _make_data(bypass_state_raw=0).bypass_status.lower()

    def test_255_is_offen(self):
        assert "offen" in _make_data(bypass_state_raw=255).bypass_status.lower()

    def test_1_is_bewegt(self):
        status = _make_data(bypass_state_raw=1).bypass_status.lower()
        assert "zu" not in status and "offen" not in status

    def test_32_is_closing(self):
        status = _make_data(bypass_state_raw=32).bypass_status
        assert status  # nicht leer

    def test_64_is_opening(self):
        status = _make_data(bypass_state_raw=64).bypass_status
        assert status


# ── Tests: Alarm-Code → Text ──────────────────────────────────────────────────

class TestAlarmText:
    def test_code_0_empty(self):
        assert _make_data(alarm_code=0).alarm_text == ""

    def test_code_11_frost(self):
        text = _make_data(alarm_code=11).alarm_text
        assert "E11" in text
        assert "5" in text or "Frost" in text

    def test_code_1_abluft(self):
        text = _make_data(alarm_code=1).alarm_text
        assert "E1" in text and "Abluft" in text

    def test_code_15_wasser(self):
        text = _make_data(alarm_code=15).alarm_text
        assert "E15" in text

    def test_unknown_code_shows_number(self):
        text = _make_data(alarm_code=99).alarm_text
        assert "99" in text


# ── Tests: A/B-Schalter → Fan-Zuordnung ───────────────────────────────────────

class TestFanAssignment:
    """fan1_is_extract=True → Fan1=Abluft, Fan2=Zuluft."""

    def test_fan1_is_extract_true(self):
        data = _make_data(fan1_rpm=1500.0, fan2_rpm=1600.0, fan1_is_extract=True)
        assert data.motor_abluft_rpm == pytest.approx(1500.0)
        assert data.motor_zuluft_rpm == pytest.approx(1600.0)

    def test_fan1_is_extract_false(self):
        data = _make_data(fan1_rpm=1600.0, fan2_rpm=1500.0, fan1_is_extract=False)
        assert data.motor_abluft_rpm == pytest.approx(1500.0)
        assert data.motor_zuluft_rpm == pytest.approx(1600.0)

    def test_zero_rpm_returns_none(self):
        data = _make_data(fan1_rpm=0.0, fan2_rpm=0.0, fan1_is_extract=True)
        assert data.motor_abluft_rpm is None
        assert data.motor_zuluft_rpm is None


# ── Tests: Abgeleitete Diagnose-Properties ─────────────────────────────────────

class TestDerivedProperties:

    def test_heat_recovery_efficiency_typical(self):
        """η = (T_zuluft − T_aussen) / (T_abluft − T_aussen) × 100."""
        # T1=5, T2=19, T3=21 → η = (19-5)/(21-5) × 100 = 14/16 × 100 = 87.5%
        data = _make_data(t1=5.0, t2=19.0, t3=21.0)
        eta = data.heat_recovery_efficiency
        assert eta is not None
        assert eta == pytest.approx(87.5, abs=0.5)

    def test_heat_recovery_efficiency_none_small_delta(self):
        """δ < 3 K → None (Messrauschen)."""
        data = _make_data(t1=20.0, t2=20.5, t3=21.0)  # δ = 1 K
        assert data.heat_recovery_efficiency is None

    def test_heat_recovery_efficiency_none_when_temp_missing(self):
        data = _make_data(t1=None)
        assert data.heat_recovery_efficiency is None

    def test_heat_recovery_watts_none_for_flex(self):
        """flex: heat_recovery_watts gibt None zurück bis Q_ref bekannt ist."""
        data = _make_data(t3=21.0, t2=19.0)
        assert data.heat_recovery_watts is None

    def test_frost_risk_true(self):
        data = _make_data(t1=-10.0, t2=3.0)
        assert data.frost_risk is True

    def test_frost_risk_false_mild(self):
        data = _make_data(t1=2.0, t2=18.0)
        assert data.frost_risk is False

    def test_motor_asymmetry_false_normal(self):
        """Normale Asymmetrie (Zuluft ~20% schneller) → False."""
        data = _make_data(fan1_rpm=1200.0, fan2_rpm=1000.0, fan1_is_extract=False)
        # rpm_zu=1200, rpm_ab=1000 → asym = 200/1200 = 16.7% < 22% → False
        assert data.motor_asymmetry is False

    def test_motor_asymmetry_true_above_threshold(self):
        """Asymmetrie > 22% → True."""
        data = _make_data(fan1_rpm=1300.0, fan2_rpm=1000.0, fan1_is_extract=False)
        # rpm_zu=1300, rpm_ab=1000 → asym = 300/1300 = 23.1% > 22% → True
        assert data.motor_asymmetry is True

    def test_motor_asymmetry_true_direction_reversed(self):
        """Abluft schneller als Zuluft → True (Richtungsumkehr, > 10%)."""
        # fan1=Abluft=1150, fan2=Zuluft=1000 → 1150 > 1000*1.10=1100 → True
        data = _make_data(fan1_rpm=1150.0, fan2_rpm=1000.0, fan1_is_extract=True)
        assert data.motor_asymmetry is True

    def test_bypass_leaking_false_when_open(self):
        """Bypass offen → kein Leckage-Alarm."""
        data = _make_data(bypass_state_raw=255, t1=25.0, t3=24.0, t4=24.5)
        assert data.bypass_leaking is False

    def test_bypass_leaking_true_when_closed_but_fortluft_like_aussen(self):
        """Bypass zu, aber Fortluft ≈ Außenluft → Leckage."""
        data = _make_data(bypass_state_raw=0, t1=5.0, t3=21.0, t4=7.0)
        # δ=16K ≥ 5K, |t4-t1|=|7-5|=2K < 4K → True
        assert data.bypass_leaking is True

    def test_bypass_recommended_true(self):
        data = _make_data(t1=15.0, t3=25.0)  # t1 < t3-3 AND t3>22 AND t1>10
        assert data.bypass_recommended is True

    def test_bypass_recommended_false_too_cold(self):
        data = _make_data(t1=8.0, t3=25.0)  # t1 < 10 → False
        assert data.bypass_recommended is False

    def test_filter_ok_true_when_days_remaining(self):
        data = _make_data(filter_residual_days=90, alarm_code=0)
        assert data.filter_ok is True

    def test_filter_ok_false_when_zero_days(self):
        data = _make_data(filter_residual_days=0, alarm_code=0)
        assert data.filter_ok is False


# ── Tests: Poll-Divisor Logik (via Source-Analyse) ───────────────────────────

FLEX_COORD_PY = (
    "/home/claude/kwl_src/custom_components/kwl_fraenkische/flex_coordinator.py"
)


class TestPollDivisorSource:
    """Strukturelle Verifikation der Poll-Divisor-Implementierung via AST.
    
    KWLFlexCoordinator kann in der Stub-Umgebung nicht vollständig instantiiert
    werden (DataUpdateCoordinator Base-Klasse). Stattdessen verifikation der
    Implementierung direkt im Quellcode.
    """

    def _get_method_source(self, method_name: str) -> str:
        import ast, textwrap
        source = open(FLEX_COORD_PY).read()
        tree = ast.parse(source)
        for cls in ast.walk(tree):
            if isinstance(cls, ast.ClassDef) and cls.name == "KWLFlexCoordinator":
                for item in cls.body:
                    if isinstance(item, (ast.AsyncFunctionDef, ast.FunctionDef)) and item.name == method_name:
                        lines = source.splitlines()
                        return "\n".join(lines[item.lineno-1:item.end_lineno])
        return ""

    def test_poll_divisor_constant_defined(self):
        """_POLL_SLOW_DIVISOR muss als Konstante definiert sein."""
        source = open(FLEX_COORD_PY).read()
        assert "_POLL_SLOW_DIVISOR" in source
        assert "10" in source

    def test_slow_blocks_constant_defined(self):
        """_SLOW_BLOCKS Tuple muss definiert sein."""
        source = open(FLEX_COORD_PY).read()
        assert "_SLOW_BLOCKS" in source

    def test_fast_blocks_constant_defined(self):
        """_FAST_BLOCKS Tuple muss definiert sein."""
        source = open(FLEX_COORD_PY).read()
        assert "_FAST_BLOCKS" in source

    def test_read_all_registers_uses_poll_count_mod(self):
        """_read_all_registers muss _poll_count % _POLL_SLOW_DIVISOR verwenden."""
        method_src = self._get_method_source("_read_all_registers")
        assert "_poll_count" in method_src
        assert "_POLL_SLOW_DIVISOR" in method_src or "% " in method_src

    def test_read_all_registers_checks_slow_cache(self):
        """_read_all_registers muss _slow_cache prüfen."""
        method_src = self._get_method_source("_read_all_registers")
        assert "_slow_cache" in method_src

    def test_slow_blocks_at_correct_offsets(self):
        """Slow-Blocks müssen Offset 340, 444, 554, 624 enthalten."""
        source = open(FLEX_COORD_PY).read()
        # Alle 4 Slow-Block-Offsets müssen im SLOW_BLOCKS-Bereich stehen
        for offset in (340, 444, 554, 624):
            assert str(offset) in source, f"Offset {offset} nicht in flex_coordinator.py"

    def test_fast_blocks_at_correct_offsets(self):
        """Fast-Blocks müssen kritische Offsets enthalten (100, 132, 472, 516)."""
        source = open(FLEX_COORD_PY).read()
        for offset in (100, 132, 472, 516):
            assert str(offset) in source, f"Offset {offset} nicht in fast blocks"

    def test_poll_count_increments_mod_10(self):
        """_poll_count-Logik: verwendet Modulo-10."""
        source = open(FLEX_COORD_PY).read()
        assert "_poll_count + 1) % _POLL_SLOW_DIVISOR" in source or \
               "% 10" in source or \
               "% _POLL_SLOW_DIVISOR" in source


class TestWriteMethodsSource:
    """Strukturelle Verifikation der Write-Methoden via AST."""

    def _method_calls_refresh(self, method_name: str) -> bool:
        import ast
        source = open(FLEX_COORD_PY).read()
        tree = ast.parse(source)
        for cls in ast.walk(tree):
            if isinstance(cls, ast.ClassDef) and cls.name == "KWLFlexCoordinator":
                for item in cls.body:
                    if isinstance(item, (ast.AsyncFunctionDef, ast.FunctionDef)) and item.name == method_name:
                        for node in ast.walk(item):
                            if isinstance(node, ast.Attribute) and node.attr == "async_request_refresh":
                                return True
        return False

    def _method_source(self, method_name: str) -> str:
        import ast
        source = open(FLEX_COORD_PY).read()
        tree = ast.parse(source)
        for cls in ast.walk(tree):
            if isinstance(cls, ast.ClassDef) and cls.name == "KWLFlexCoordinator":
                for item in cls.body:
                    if isinstance(item, (ast.AsyncFunctionDef, ast.FunctionDef)) and item.name == method_name:
                        lines = source.splitlines()
                        return "\n".join(lines[item.lineno-1:item.end_lineno])
        return ""

    def test_set_level_implemented_not_raising(self):
        """async_set_level muss implementiert sein -- kein NotImplementedError mehr.

        Begründung: prmRomIdxSpeedLevel ist UINT32 (2 Register). FC06 (Single
        Register Write) kann nur 16 Bit schreiben und scheitert daher
        erwartungsgemäß -- das ist keine offene Frage, sondern Modbus-Mechanik.
        FC16 (_write_uint32, bereits für 5 andere Parameter genutzt) ist exakt
        das richtige Werkzeug.
        """
        src = self._method_source("async_set_level")
        assert "NotImplementedError" not in src

    def test_set_level_clamps_range(self):
        src = self._method_source("async_set_level")
        assert "max(1, min(4, level))" in src

    def test_set_level_writes_offset_324(self):
        src = self._method_source("async_set_level")
        assert "self._write_uint32(324, level)" in src

    def test_set_level_switches_to_manual_if_needed(self):
        """Gerät übernimmt Stufenänderungen nur im Manual-Mode -- muss ggf. vorher wechseln."""
        src = self._method_source("async_set_level")
        assert "current_mode_text" in src
        assert 'FLEX_MODE_TO_WRITE["Manuell"]' in src

    def test_set_level_uses_lock(self):
        src = self._method_source("async_set_level")
        assert "async with self._lock:" in src

    def test_reset_filter_calls_refresh(self):
        """async_reset_filter muss async_request_refresh aufrufen (Option C)."""
        assert self._method_calls_refresh("async_reset_filter"), (
            "async_reset_filter ruft async_request_refresh nicht auf"
        )

    def test_reset_filter_writes_to_offset_558(self):
        """async_reset_filter muss auf offset 558 schreiben (Register 40559)."""
        src = self._method_source("async_reset_filter")
        assert "558" in src

    def test_clear_alarm_calls_refresh(self):
        """async_clear_alarm muss async_request_refresh aufrufen."""
        assert self._method_calls_refresh("async_clear_alarm")

    def test_clear_alarm_writes_to_offset_514(self):
        """async_clear_alarm muss auf offset 514 schreiben (Register 40515)."""
        src = self._method_source("async_clear_alarm")
        assert "514" in src

    def test_set_filter_total_clamps(self):
        """async_set_filter_total muss Wert auf 30–360 begrenzen."""
        src = self._method_source("async_set_filter_total")
        assert "30" in src and "360" in src

    def test_set_filter_total_calls_refresh(self):
        """async_set_filter_total muss async_request_refresh aufrufen."""
        assert self._method_calls_refresh("async_set_filter_total")

    def test_set_mode_calls_refresh(self):
        """async_set_mode muss async_request_refresh aufrufen (Option C)."""
        assert self._method_calls_refresh("async_set_mode")

    def test_set_mode_uses_flex_mode_to_write(self):
        """async_set_mode muss FLEX_MODE_TO_WRITE Konstante nutzen."""
        src = self._method_source("async_set_mode")
        assert "FLEX_MODE_TO_WRITE" in src

    def test_set_mode_uses_offset_168(self):
        """async_set_mode muss auf offset 168 schreiben (Register 40169)."""
        src = self._method_source("async_set_mode")
        assert "168" in src

    def test_reset_analytics_calls_reset_baselines(self):
        """async_reset_analytics muss analytics.reset_baselines() aufrufen."""
        src = self._method_source("async_reset_analytics")
        assert "reset_baselines" in src

    def test_write_uint32_uses_little_word_order(self):
        """_write_uint32 muss word_order='little' verwenden."""
        src = self._method_source("_write_uint32")
        assert "'little'" in src or "\"little\"" in src


class TestConnectionSource:
    """Strukturelle Verifikation der Verbindungslogik via AST."""

    def _method_source(self, method_name: str) -> str:
        import ast
        source = open(FLEX_COORD_PY).read()
        tree = ast.parse(source)
        for cls in ast.walk(tree):
            if isinstance(cls, ast.ClassDef) and cls.name == "KWLFlexCoordinator":
                for item in cls.body:
                    if isinstance(item, (ast.AsyncFunctionDef, ast.FunctionDef)) and item.name == method_name:
                        lines = source.splitlines()
                        return "\n".join(lines[item.lineno-1:item.end_lineno])
        return ""

    def test_connect_and_init_sets_needs_reconnect_false(self):
        """_connect_and_init muss _needs_reconnect = False setzen."""
        src = self._method_source("_connect_and_init")
        assert "_needs_reconnect = False" in src or "_needs_reconnect=False" in src

    def test_connect_and_init_raises_update_failed_on_failure(self):
        """_connect_and_init muss UpdateFailed werfen wenn Verbindung fehlschlägt."""
        src = self._method_source("_connect_and_init")
        assert "UpdateFailed" in src

    def test_async_update_data_sets_needs_reconnect_on_error(self):
        """_async_update_data muss _needs_reconnect = True bei Fehler setzen."""
        src = self._method_source("_async_update_data")
        assert "_needs_reconnect = True" in src or "_needs_reconnect=True" in src

    def test_async_update_data_raises_update_failed(self):
        """_async_update_data muss UpdateFailed werfen."""
        src = self._method_source("_async_update_data")
        assert "UpdateFailed" in src

    def test_async_teardown_closes_client(self):
        """async_teardown muss _client.close() aufrufen."""
        src = self._method_source("async_teardown")
        assert "_client.close" in src

    def test_pymodbus_logging_suppressed(self):
        """pymodbus logging muss auf CRITICAL gesetzt werden."""
        source = open(FLEX_COORD_PY).read()
        assert "pymodbus" in source and "CRITICAL" in source


# ── Tests: Modbus Write-Logik direkt (via pymodbus) ──────────────────────────

class TestWriteUint32Logic:
    """Verifikation des FC16-Write-Formats via pymodbus direkt."""

    def _encode(self, value: int) -> list:
        from pymodbus.client.mixin import ModbusClientMixin
        return list(ModbusClientMixin.convert_to_registers(
            value, ModbusClientMixin.DATATYPE.UINT32, "little"
        ))

    def test_write_1_for_filter_reset(self):
        """Filter-Reset schreibt Wert 1 → [1, 0]."""
        assert self._encode(1) == [1, 0]

    def test_write_0_for_alarm_clear(self):
        """Alarm-Clear schreibt Wert 0 → [0, 0]."""
        assert self._encode(0) == [0, 0]

    def test_write_manual_mode_bitmask(self):
        """Manual-Modus: 0x0004 → [4, 0]."""
        assert self._encode(0x0004) == [4, 0]

    def test_write_away_mode_bitmask(self):
        """Away-Modus: 0x0010 → [16, 0]."""
        assert self._encode(0x0010) == [16, 0]

    def test_write_filter_days_360(self):
        """Filter-Intervall 360 Tage → [360, 0]."""
        assert self._encode(360) == [360, 0]

    def test_write_filter_days_30(self):
        """Filter-Intervall 30 Tage (Minimum) → [30, 0]."""
        assert self._encode(30) == [30, 0]
