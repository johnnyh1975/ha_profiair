"""Tests für die Erkenntnisse aus der Hersteller-App (Cockpit 1.0.23).

Abgedeckt:
- Modus: BL-Zustände 9/16 zusätzlich zu 7/12, Konfliktauflösung per
  Modus-Bitmaske (Register 168), Rückfall auf die Doku-Zuordnung ohne Bitmaske
- Alarm: aktive Alarme aus der Bitmaske (Register 170), has_alarm, alarm_text
- Optionaler Lesebock 168..171: Dekodierung, fehlertolerant, Selbstabschaltung
- Schreibfolgen: Alarm-Quittung mit Code, Sommer ein/aus mit Register 476,
  476-Fehler ist nicht fatal
"""
from __future__ import annotations

import importlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pymodbus.exceptions import ModbusIOException


def _mod():
    return importlib.import_module("custom_components.kwl_fraenkische.flex_coordinator")


def _const():
    return importlib.import_module("custom_components.kwl_fraenkische.const")


def _data(**overrides):
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
    return _mod().KWLFlexData(**defaults)


NIGHT, FIRE = 0x0020, 0x0040


# ── Modus ─────────────────────────────────────────────────────────────────────

class TestModeMapping:
    def test_app_states_9_and_16(self):
        assert _data(current_mode=9).current_mode_slug == "fireplace"
        assert _data(current_mode=16).current_mode_slug == "night"
        assert _data(current_mode=9).current_mode_text == "Kaminbetrieb"
        assert _data(current_mode=16).current_mode_text == "Nacht"

    def test_legacy_states_unchanged_without_bitmask(self):
        """Ohne lesbare Bitmaske bleibt die bisherige Doku-Zuordnung."""
        assert _data(current_mode=7).current_mode_slug == "night"
        assert _data(current_mode=12).current_mode_slug == "fireplace"

    def test_state_12_with_fireplace_flag_is_fireplace(self):
        d = _data(current_mode=12, unit_mode_mask=FIRE | 0x04)
        assert d.current_mode_slug == "fireplace"
        assert d.current_mode_text == "Kaminbetrieb"

    def test_state_12_without_fireplace_flag_is_not_fireplace(self):
        d = _data(current_mode=12, unit_mode_mask=0x04)
        assert d.current_mode_slug is None
        assert d.current_mode_text == "Störungsbetrieb 2"

    def test_state_7_with_night_flag_is_night(self):
        assert _data(current_mode=7, unit_mode_mask=NIGHT | 0x02).current_mode_slug == "night"

    def test_state_7_without_night_flag_is_not_night(self):
        d = _data(current_mode=7, unit_mode_mask=0x02)
        assert d.current_mode_slug is None
        assert d.current_mode_text == "Digitaleingang-Übersteuerung"

    def test_state_16_unaffected_by_bitmask(self):
        assert _data(current_mode=16, unit_mode_mask=0).current_mode_slug == "night"

    def test_regular_modes_unaffected_by_bitmask(self):
        for mode, slug in ((1, "manual"), (2, "demand"), (3, "weekly_schedule"),
                           (5, "away"), (6, "summer")):
            assert _data(current_mode=mode, unit_mode_mask=0).current_mode_slug == slug

    def test_extra_state_texts(self):
        assert _data(current_mode=0).current_mode_text == "Standby"
        assert _data(current_mode=15).current_mode_text == "Abtauen"
        assert _data(current_mode=0).current_mode_slug is None
        assert _data(current_mode=99).current_mode_text == "Modus 99"

    def test_text_and_slug_maps_have_same_keys(self):
        c = _const()
        assert set(c.FLEX_MODE_TEXT) == set(c.FLEX_MODE_SLUG)

    def test_extra_texts_do_not_shadow_slug_states(self):
        c = _const()
        assert not set(c.FLEX_BL_STATE_EXTRA_TEXT) & set(c.FLEX_MODE_TEXT)

    def test_all_slug_targets_are_writable(self):
        c = _const()
        assert set(c.FLEX_MODE_SLUG.values()) <= set(c.FLEX_MODE_TO_WRITE)


# ── Alarm ─────────────────────────────────────────────────────────────────────

class TestAlarmBitmask:
    def test_bit_table_maps_to_known_alarm_codes(self):
        c = _const()
        assert set(c.FLEX_ALARM_BIT_TO_CODE.values()) <= set(c.FLEX_ALARM_TEXT)
        assert len(set(c.FLEX_ALARM_BIT_TO_CODE.values())) == len(c.FLEX_ALARM_BIT_TO_CODE)
        assert all(bin(b).count("1") == 1 for b in c.FLEX_ALARM_BIT_TO_CODE)

    def test_known_bits(self):
        assert _data(alarm_mask=0x0020).active_alarm_codes == (1,)      # E1 Abluft
        assert _data(alarm_mask=0x0001).active_alarm_codes == (4,)      # E4 T1
        assert _data(alarm_mask=0x8000).active_alarm_codes == (3,)      # E3 Bypass
        assert _data(alarm_mask=0x0400).active_alarm_codes == (15,)     # E15 Kondensat

    def test_multiple_alarms_sorted(self):
        d = _data(alarm_mask=0x0020 | 0x0001 | 0x0100)
        assert d.active_alarm_codes == (1, 4, 11)

    def test_no_mask_or_zero_mask(self):
        assert _data().active_alarm_codes == ()
        assert _data(alarm_mask=0).active_alarm_codes == ()

    def test_has_alarm_combines_both_sources(self):
        assert not _data(alarm_code=0, alarm_mask=0).has_alarm
        assert not _data(alarm_code=0, alarm_mask=None).has_alarm
        assert _data(alarm_code=2, alarm_mask=0).has_alarm        # gespeichert (516)
        assert _data(alarm_code=0, alarm_mask=0x0040).has_alarm   # aktiv (170)

    def test_alarm_text_lists_all_active_alarms(self):
        d = _data(alarm_code=1, alarm_mask=0x0020 | 0x0001)
        assert "E1" in d.alarm_text and "E4" in d.alarm_text

    def test_alarm_text_single_alarm_unchanged(self):
        assert _data(alarm_code=11).alarm_text == _const().FLEX_ALARM_TEXT[11]
        assert _data(alarm_code=1, alarm_mask=0x0020).alarm_text == _const().FLEX_ALARM_TEXT[1]

    def test_alarm_text_from_mask_when_516_empty(self):
        assert _data(alarm_code=0, alarm_mask=0x0040).alarm_text == _const().FLEX_ALARM_TEXT[2]

    def test_alarm_text_empty_without_alarm(self):
        assert _data().alarm_text == ""


# ── Optionaler Lesebock ───────────────────────────────────────────────────────

def _coordinator():
    m = _mod()
    c = m.KWLFlexCoordinator.__new__(m.KWLFlexCoordinator)
    c._lock = __import__("asyncio").Lock()
    c._poll_count = 0
    c._slow_cache = {}
    c._optional_fails = 0
    c.capabilities = None
    c.watt_map = {1: None, 2: None, 3: None, 4: None}
    c._analytics = None
    c.data = None
    c.async_request_refresh = AsyncMock()
    return c


def _reply(count, error=False, regs=None):
    r = MagicMock()
    r.isError.return_value = error
    r.registers = regs if regs is not None else [0] * count
    return r


def _client(optional_reply):
    async def read(address, count, device_id):
        if address == 168:
            return optional_reply(count)
        return _reply(count)
    client = MagicMock()
    client.read_holding_registers = AsyncMock(side_effect=read)
    return client


class TestOptionalBlock:
    def test_decoded_into_masks(self):
        c = _coordinator()
        # 168/169 = 0x00000024 (Manual+Night), 170/171 = 0x00000021 (E1 + E4)
        raw = {"o_168": [0x0024, 0x0000, 0x0021, 0x0000]}
        d = c._build_data(raw)
        assert d.unit_mode_mask == 0x24
        assert d.alarm_mask == 0x21
        assert d.active_alarm_codes == (1, 4)

    def test_absent_block_gives_none(self):
        d = _coordinator()._build_data({})
        assert d.unit_mode_mask is None and d.alarm_mask is None

    @pytest.mark.asyncio
    async def test_read_success_adds_block(self):
        c = _coordinator()
        c._client = _client(lambda n: _reply(n, regs=[4, 0, 0, 0]))
        raw = await c._read_all_registers()
        assert raw["o_168"] == [4, 0, 0, 0]

    @pytest.mark.asyncio
    async def test_device_error_is_not_fatal_and_disables_block(self):
        c = _coordinator()
        c._client = _client(lambda n: _reply(n, error=True))
        for _ in range(3):
            raw = await c._read_all_registers()
            assert "o_168" not in raw
            assert "f_472" in raw          # Fast-Blocks laufen normal weiter
        assert c._optional_fails == 3
        calls_before = sum(
            1 for ca in c._client.read_holding_registers.await_args_list
            if ca.kwargs["address"] == 168
        )
        await c._read_all_registers()
        calls_after = sum(
            1 for ca in c._client.read_holding_registers.await_args_list
            if ca.kwargs["address"] == 168
        )
        assert calls_after == calls_before   # nicht mehr versucht

    @pytest.mark.asyncio
    async def test_short_reply_counts_as_failure(self):
        c = _coordinator()
        c._client = _client(lambda n: _reply(n, regs=[1, 2]))
        raw = await c._read_all_registers()
        assert "o_168" not in raw and c._optional_fails == 1

    @pytest.mark.asyncio
    async def test_success_resets_failure_counter(self):
        c = _coordinator()
        c._optional_fails = 2
        c._client = _client(lambda n: _reply(n))
        await c._read_all_registers()
        assert c._optional_fails == 0

    @pytest.mark.asyncio
    async def test_transport_error_still_propagates(self):
        c = _coordinator()
        client = MagicMock()
        client.read_holding_registers = AsyncMock(side_effect=ModbusIOException("weg"))
        c._client = client
        with pytest.raises(ModbusIOException):
            await c._read_all_registers()


# ── Schreibfolgen ─────────────────────────────────────────────────────────────

def _recording(c, fail_offsets=()):
    writes: list[tuple[int, int]] = []

    async def write(offset, value):
        if offset in fail_offsets:
            raise ModbusIOException("abgelehnt")
        writes.append((offset, value))

    c._write_uint32 = write
    return writes


class TestWriteSequences:
    @pytest.mark.asyncio
    async def test_clear_alarm_writes_alarm_code(self):
        c = _coordinator()
        c.data = _data(alarm_code=4)
        writes = _recording(c)
        await c.async_clear_alarm()
        assert writes == [(514, 4)]
        c.async_request_refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_clear_alarm_without_data_writes_zero(self):
        c = _coordinator()
        writes = _recording(c)
        await c.async_clear_alarm()
        assert writes == [(514, 0)]

    @pytest.mark.asyncio
    async def test_summer_on_writes_mask_then_required_state(self):
        c = _coordinator()
        c.data = _data(current_mode=1)
        writes = _recording(c)
        await c.async_set_mode("summer")
        assert writes == [(168, 0x0800), (476, 6)]

    @pytest.mark.asyncio
    async def test_summer_off_follows_app_sequence(self):
        c = _coordinator()
        c.data = _data(current_mode=6)
        writes = _recording(c)
        with patch("asyncio.sleep", new=AsyncMock()) as sleep:
            await c.async_set_mode("manual")
        assert writes == [(168, 0x8800), (476, 6), (476, 0), (168, 0x0004)]
        assert any(ca.args == (1.5,) for ca in sleep.await_args_list)

    @pytest.mark.asyncio
    async def test_required_state_failure_is_not_fatal(self):
        c = _coordinator()
        c.data = _data(current_mode=1)
        writes = _recording(c, fail_offsets=(476,))
        await c.async_set_mode("summer")
        assert writes == [(168, 0x0800)]
        c.async_request_refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_other_modes_do_not_touch_register_476(self):
        c = _coordinator()
        c.data = _data(current_mode=1)
        writes = _recording(c)
        for mode in ("demand", "away", "night", "fireplace", "weekly_schedule"):
            await c.async_set_mode(mode)
        assert all(off != 476 for off, _ in writes)

    @pytest.mark.asyncio
    async def test_leaving_away_writes_only_end_mask(self):
        c = _coordinator()
        c.data = _data(current_mode=5)
        writes = _recording(c)
        with patch("asyncio.sleep", new=AsyncMock()):
            await c.async_set_mode("manual")
        assert writes == [(168, 0x8010), (168, 0x0004)]
