"""Modbus TCP Coordinator für profi-air 250/360 flex und profi-air 180 flat.

Protokoll:
  - Modbus TCP, Port 502
  - FC03 (Read Holding Registers), FC16 (Write Multiple Registers)
  - Alle 32-bit-Parameter: Low-Register zuerst, Float CDAB → word_order='little'

Polling-Strategie (A+C):
  A) Poll-Divisor: operative Register (Temps, RPM, Stufe, Alarm …) bei jedem
     Poll; quasi-statische Register (Filter, Bypass-Schwellen, Work Time …)
     nur alle _POLL_SLOW_DIVISOR = 10 Polls (~5 min bei 30 s Intervall).
  C) Reflektives Polling: alle async_set_*()-Methoden rufen am Ende
     async_request_refresh() auf — sofortige UI-Bestätigung ohne 30 s Wartezeit.

Registertabelle: docs/flex-modbus.md
"""
from __future__ import annotations

import asyncio
import logging
import time as _time
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.client.mixin import ModbusClientMixin
from pymodbus.exceptions import ModbusIOException

from .analytics import (
    ANALYTICS_STORAGE_KEY_PREFIX,
    ANALYTICS_STORAGE_VERSION,
    KWLAnalytics,
    KWLPollSnapshot,
)
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_WATT_LEVEL_1,
    CONF_WATT_LEVEL_2,
    CONF_WATT_LEVEL_3,
    CONF_WATT_LEVEL_4,
    DEFAULT_MODBUS_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FLEX_ALARM_TEXT,
    FLEX_MODE_TEXT,
    FLEX_MODE_TO_END,
    FLEX_MODE_TO_WRITE,
    FILTER_RPM_DRIFT_WARN_PCT,
    MODEL_DISPLAY,
    MODEL_PROFI_AIR_360_FLEX,
    UNIT_TYPE_TO_MODEL,
    WATT_DEFAULTS,
)

_LOGGER = logging.getLogger(__name__)

# ── Modbus Batch-Read-Blöcke (offset = Registeradresse − 40001) ───────────────

# Operativer Datensatz — jeder Poll-Zyklus
_FAST_BLOCKS: Final[tuple[tuple[int, int], ...]] = (
    (100, 4),   # 40101/40103: Fan1 RPM (FLOAT), Fan2 RPM (FLOAT)
    (132, 10),  # 40133–40142: T1-T5 (je FLOAT)
    (160, 2),   # 40161: Preheater Duty % (UINT32)
    (196, 4),   # 40197: RH % (UINT32), 40199: Bypass State (UINT32)
    (324, 2),   # 40325: Fan Level (UINT32)
    (430, 2),   # 40431: VOC ppm (UINT32)
    (472, 2),   # 40473: Current Mode (UINT32)
    (516, 2),   # 40517: Alarm Code (UINT32)  – 40515 (alarm clear) übersprungen
    (574, 2),   # 40575: CO2 ppm (UINT32)
)

# Quasi-statischer Datensatz — alle _POLL_SLOW_DIVISOR Polls
_SLOW_BLOCKS: Final[tuple[tuple[int, int], ...]] = (
    (340, 2),   # 40341: RH Setpoint % (UINT32)
    (444, 4),   # 40445: Bypass Tmin (FLOAT), 40447: Bypass Tmax (FLOAT)
    (554, 6),   # 40555: Filter Remaining (UINT32), 40557: Filter Total (UINT32)
                #   40559: Filter Reset (write-only, lesen liefert 0)
    (624, 2),   # 40625: Work Time h (UINT32)
)

# Einmalig beim Setup
_SETUP_BLOCKS: Final[tuple[tuple[int, int], ...]] = (
    (2,   2),   # 40003: System ID (UINT32) → Byte 0 = Unit-Typ
    (24,  2),   # 40025: Firmware Version (UINT32)
    (40,  4),   # 40041: MAC Addr High (UINT32), 40043: MAC Addr Low (UINT32)
    (84,  4),   # 40085: HALLeft (UINT32), 40087: HALRight (UINT32)
    (518, 4),   # 40519: Ref RPM Extract S3 (UINT32), 40521: Ref RPM Supply S3 (UINT32)
)

_POLL_SLOW_DIVISOR: Final[int] = 10   # Slow-Block alle 10 Polls (~5 min @ 30 s)
_DEFECT_THRESHOLD:  Final[int] = 10   # Konsekutive Polls bevor Repair Issue erscheint
TIME_SYNC_INTERVAL: Final       = timedelta(hours=24)
ANNUAL_MAINTENANCE_HOURS: Final[int] = 8760


# ── Bypass-Status: Integer → String ──────────────────────────────────────────

_BYPASS_STATE: Final[dict[int, str]] = {
    0:   "Auto: Zu",
    1:   "Auto: Bewegt",
    32:  "Auto: Schließt",
    64:  "Auto: Öffnet",
    255: "Auto: Offen",
}


# ── KWLFlexCapabilities ───────────────────────────────────────────────────────

@dataclass
class KWLFlexCapabilities:
    """Einmalig beim Setup gelesene Geräte-Eigenschaften.

    Alle Felder sind nach dem ersten erfolgreichen Setup-Read befüllt und
    bleiben für die Lebensdauer des Coordinators konstant.
    """

    model: str                  # MODEL_PROFI_AIR_*_FLEX / _FLAT
    mac_id: str                 # Unique-ID String (hex, 16 Zeichen)
    firmware_version: str       # "Major.Minor"
    fan1_is_extract: bool       # True → Fan1 = Abluft, Fan2 = Zuluft
    ref_rpm_extract_s3: int     # Referenz-RPM Abluft bei Stufe 3 (Inbetriebnahme)
    ref_rpm_supply_s3: int      # Referenz-RPM Zuluft bei Stufe 3


# ── KWLFlexData ───────────────────────────────────────────────────────────────

class KWLFlexData:
    """Dekodierter Datensatz eines Modbus-Polls.

    Property-Namen für gemeinsame Features identisch zu KWLData (coordinator.py)
    — Entity-Plattformen müssen für diese Properties nicht geändert werden.
    """

    # ── Rohdaten (von _build_data gesetzt) ────────────────────────────────────

    def __init__(
        self,
        *,
        # Lüfter
        fan1_rpm: float,
        fan2_rpm: float,
        fan1_is_extract: bool,
        # Temperaturen
        t1: float | None,
        t2: float | None,
        t3: float | None,
        t4: float | None,
        t5: float | None,
        # Betrieb
        current_level: int,
        current_mode: int,
        preheater_duty_pct: int,
        bypass_state_raw: int,
        alarm_code: int,
        # Sensoren (optional)
        rh_percent: int | None,
        rh_setpoint: int | None,
        voc_ppm: int | None,
        co2_ppm: int | None,
        # Bypass-Schwellen
        bypass_tmin: float | None,
        bypass_tmax: float | None,
        # Filter
        filter_residual_days: int | None,
        filter_total_days: int | None,
        # Gesamtstunden
        hours_total: int | None,
        # Watt-Konfiguration
        watt_map: dict[int, float | None],
        # Inbetriebnahme-Referenz-RPM bei Stufe 3 (für Filter-Drift-Diagnose)
        ref_rpm_extract_s3: int | None = None,
        ref_rpm_supply_s3: int | None = None,
    ) -> None:
        self._fan1_rpm        = fan1_rpm
        self._fan2_rpm        = fan2_rpm
        self._fan1_is_extract = fan1_is_extract
        self._t1 = t1
        self._t2 = t2
        self._t3 = t3
        self._t4 = t4
        self._t5 = t5

        self.current_level       = current_level
        self.current_mode        = current_mode
        self.preheater_duty_pct  = preheater_duty_pct
        self._bypass_state_raw   = bypass_state_raw
        self.alarm_code          = alarm_code

        self._rh_percent  = rh_percent if (rh_percent is not None and rh_percent > 0) else None
        self.rh_setpoint  = rh_setpoint if (rh_setpoint is not None and rh_setpoint > 0) else None
        self._voc_ppm     = voc_ppm if (voc_ppm is not None and voc_ppm > 0) else None
        self._co2_ppm     = co2_ppm if (co2_ppm is not None and co2_ppm > 0) else None

        self.bypass_tmin       = bypass_tmin
        self.bypass_tmax       = bypass_tmax
        self.filter_residual_days = filter_residual_days
        self.filter_total_days    = filter_total_days
        self.hours_total          = hours_total
        self._watt_map            = watt_map
        self.ref_rpm_extract_s3   = ref_rpm_extract_s3
        self.ref_rpm_supply_s3    = ref_rpm_supply_s3

    # ── Gemeinsame Properties (identisch zu KWLData) ─────────────────────────

    @property
    def temp_aussenluft(self) -> float | None:
        return self._t1

    @property
    def temp_zuluft(self) -> float | None:
        return self._t2

    @property
    def temp_abluft(self) -> float | None:
        return self._t3

    @property
    def temp_fortluft(self) -> float | None:
        return self._t4

    @property
    def temp_room(self) -> float | None:
        """T5 Raumtemperatur (Funkfernbedienung, None wenn nicht verbaut)."""
        return self._t5

    @property
    def motor_abluft_rpm(self) -> float | None:
        """Abluft-Ventilator RPM (je nach A/B-Schalterstellung)."""
        if self._fan1_is_extract:
            return self._fan1_rpm if self._fan1_rpm > 0 else None
        return self._fan2_rpm if self._fan2_rpm > 0 else None

    @property
    def motor_zuluft_rpm(self) -> float | None:
        """Zuluft-Ventilator RPM."""
        if self._fan1_is_extract:
            return self._fan2_rpm if self._fan2_rpm > 0 else None
        return self._fan1_rpm if self._fan1_rpm > 0 else None

    @property
    def bypass_status(self) -> str:
        return _BYPASS_STATE.get(self._bypass_state_raw, f"Unbekannt ({self._bypass_state_raw})")

    @property
    def preheater_active(self) -> bool:
        return self.preheater_duty_pct > 0

    @property
    def voc_ppm(self) -> int | None:
        return self._voc_ppm

    @property
    def rh_percent(self) -> int | None:
        return self._rh_percent

    @property
    def co2_ppm(self) -> int | None:
        return self._co2_ppm

    @property
    def filter_ok(self) -> bool | None:
        if self.filter_residual_days is None:
            return None
        # Filter-Status wird ausschließlich über Resttage bestimmt.
        # Alarm-Codes E1/E2 sind Ventilator-Fehler — kein Zusammenhang mit Filter.
        return self.filter_residual_days > 0

    @property
    def current_mode_text(self) -> str:
        return FLEX_MODE_TEXT.get(self.current_mode, f"Modus {self.current_mode}")

    @property
    def alarm_text(self) -> str:
        return FLEX_ALARM_TEXT.get(self.alarm_code, f"Fehler {self.alarm_code}")

    # ── Abgeleitete Diagnose-Properties (gleiche Logik wie KWLData) ───────────

    @property
    def heat_recovery_efficiency(self) -> float | None:
        """WRG-Grad η in Prozent. Identische Formel wie touch-Modell.

        η = (T_zuluft − T_aussen) / (T_abluft − T_aussen) × 100
        Nur sinnvoll wenn T_abluft − T_aussen ≥ 3 K (sonst Messrauschen).
        """
        t_ab = self._t3
        t_zu = self._t2
        t_au = self._t1
        if t_ab is None or t_zu is None or t_au is None:
            return None
        delta = t_ab - t_au
        if delta < 3.0:
            return None
        return round((t_zu - t_au) / delta * 100, 1)

    @property
    def heat_recovery_watts(self) -> float | None:
        """Zurückgewonnene Wärmeleistung in Watt.

        Q_heat = 0.34 [Wh/(m³·K)] × Volumenstrom [m³/h] × (T_abluft − T_zuluft) [K]

        Volumenstrom-Referenz für flex-Modelle ausstehend (installations-
        spezifisch, muss bei Inbetriebnahme gemessen werden). Gibt None zurück
        bis eine Referenz verfügbar ist.

        TODO: Implementierung nach Klärung der Nennvolumenstrom-Referenz
              (z.B. via Blower-Door-Messung oder Herstellerdatenblatt).
        """
        t_ab = self._t3
        t_zu = self._t2
        if t_ab is None or t_zu is None:
            return None
        delta = t_ab - t_zu
        if delta <= 0:
            return None
        # Vorerst None — Volumenstrom-Referenz für flex ausstehend
        return None

    @property
    def frost_risk(self) -> bool:
        """True wenn Frost-Risiko am Wärmetauscher. Kriterium: T_aussen < –5 °C UND T_zuluft < 5 °C."""
        t_au = self._t1
        t_zu = self._t2
        if t_au is None or t_zu is None:
            return False
        return t_au < -5.0 and t_zu < 5.0

    @property
    def bypass_leaking(self) -> bool:
        """True wenn Bypass-Leckage vermutet wird. Identische Logik wie KWLData."""
        status = self.bypass_status.lower()
        if "offen" in status:
            return False  # Bypass soll offen sein — kein Defekt
        t_fort = self._t4
        t_au   = self._t1
        t_ab   = self._t3
        if t_fort is None or t_au is None or t_ab is None:
            return False
        delta = t_ab - t_au
        if delta >= 5.0:
            return abs(t_fort - t_au) < 4.0
        if 2.0 <= delta < 5.0 and "zu" in status:
            return abs(t_fort - t_au) < 2.0
        return False

    @property
    def motor_asymmetry(self) -> bool:
        """True wenn Motorasymmetrie > 22% oder Richtungsumkehr. Identische Logik wie KWLData."""
        rpm_zu = self.motor_zuluft_rpm
        rpm_ab = self.motor_abluft_rpm
        if rpm_zu is None or rpm_ab is None or max(rpm_zu, rpm_ab) == 0:
            return False
        if rpm_ab > rpm_zu * 1.10:  # Abluft schneller als Zuluft → Richtungsumkehr
            return True
        return abs(rpm_zu - rpm_ab) / max(rpm_zu, rpm_ab) > 0.22

    @property
    def filter_rpm_drift_pct(self) -> float | None:
        """RPM-Abweichung von der Inbetriebnahme-Referenz bei Stufe 3, in Prozent.

        Community-Beitrag (Torsten600, Juni 2026): RPM-Drift bei gleicher Stufe
        ist ein früherer Indikator für Filterverstopfung als das zeitbasierte
        Filterintervall -- ein zunehmender Druckverlust durch staubige/pollen-
        belastete Filter zwingt die EC-Motoren bei gleicher Soll-Drehzahl zu
        höherer Drehzahl, um den Volumenstrom zu halten.

        ref_rpm_extract_s3 / ref_rpm_supply_s3 (Register 40519/40521) wurden bei
        der Inbetriebnahme NUR für Stufe 3 erfasst -- die Berechnung ist daher
        nur bei aktueller Stufe 3 gültig. Bei anderen Stufen wird None
        zurückgegeben statt eines irreführenden Wertes.

        Positiver Wert = aktuelle RPM höher als Referenz (typisch bei
        zunehmendem Filterwiderstand). Schwellenwert für eine Diagnose-Warnung
        liegt bewusst nicht hier -- siehe FILTER_RPM_DRIFT_WARN_PCT.
        """
        if self.current_level != 3:
            return None
        ref_extract = self.ref_rpm_extract_s3
        ref_supply = self.ref_rpm_supply_s3
        rpm_ab = self.motor_abluft_rpm
        rpm_zu = self.motor_zuluft_rpm
        if not ref_extract or not ref_supply or rpm_ab is None or rpm_zu is None:
            return None

        drift_extract = (rpm_ab - ref_extract) / ref_extract * 100.0
        drift_supply = (rpm_zu - ref_supply) / ref_supply * 100.0
        # Konservativ: die größere der beiden Abweichungen melden
        return round(max(drift_extract, drift_supply), 1)

    @property
    def filter_rpm_drift_warning(self) -> bool:
        """True wenn die RPM-Drift bei Stufe 3 den Warnschwellenwert überschreitet.

        Ergänzt die zeitbasierte Filterwarnung um einen belastungsabhängigen
        Frühindikator -- relevant in Umgebungen mit hoher Staub-/Pollenlast,
        wo das feste Zeitintervall zu spät warnen würde.
        """
        drift = self.filter_rpm_drift_pct
        return drift is not None and drift >= FILTER_RPM_DRIFT_WARN_PCT

    @property
    def bypass_recommended(self) -> bool:
        """True wenn Sommer-Bypass gerade sinnvoll wäre. Identische Logik wie KWLData."""
        t_au = self._t1
        t_ab = self._t3
        if t_au is None or t_ab is None:
            return False
        return t_au < t_ab - 3.0 and t_ab > 22.0 and t_au > 10.0


# ── KWLFlexCoordinator ────────────────────────────────────────────────────────

class KWLFlexCoordinator(DataUpdateCoordinator[KWLFlexData]):
    """DataUpdateCoordinator für profi-air flex/flat Geräte (Modbus TCP).

    Polling-Strategie (A + C):
    A  Fast/Slow-Divisor: operative Register bei jedem Poll,
       quasi-statische Register alle 10 Polls.
    C  Post-Write-Refresh: alle Write-Methoden rufen async_request_refresh()
       auf für sofortige UI-Bestätigung.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        self._host: str = entry.data[CONF_HOST]
        self._port: int = entry.data.get("port", DEFAULT_MODBUS_PORT)

        scan_seconds = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name="KWL Fränkische Flex",
            update_interval=timedelta(seconds=scan_seconds),
            config_entry=entry,
        )

        # Pymodbus-Client (noch nicht verbunden)
        self._client = AsyncModbusTcpClient(
            host=self._host,
            port=self._port,
            timeout=3,
            retries=1,
        )
        self._lock = asyncio.Lock()
        self._needs_reconnect: bool = True   # True → verbindet beim ersten Update

        # Capabilities (befüllt nach erstem Setup-Read)
        self.capabilities: KWLFlexCapabilities | None = None

        # Poll-Divisor (Option A)
        self._poll_count: int = 0
        self._slow_cache: dict[str, Any] | None = None

        # Watt-Konfiguration aus Options / Data
        self.watt_map: dict[int, float | None] = self._build_watt_map(entry)

        # Analytics + persistente Speicherung
        self._analytics: KWLAnalytics | None = None
        self._store: Store | None = None

        # Repair-Issue-Counter
        self._bypass_leak_count: int = 0
        self._motor_asym_count: int = 0

        # Wartungsgrenze aus entry.data (nicht options, um ungewollten Reload zu vermeiden)
        self._maintenance_next_threshold: float = entry.data.get(
            "maintenance_next_threshold", float(ANNUAL_MAINTENANCE_HOURS)
        )

        # Zähler für gedrosseltes Logging fehlgeschlagener Zeitsynchronisation
        self._time_sync_failures = 0

        # DeviceInfo wird nach erstem Setup-Read befüllt
        self.device_info: DeviceInfo = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},  # vorläufig bis MAC bekannt
            name="profi-air flex",
            manufacturer="Fränkische Rohrwerke",
        )

    # ── Öffentliche Setup/Teardown-Methoden ──────────────────────────────────

    async def async_setup(self) -> None:
        """Wird aus __init__.py nach dem ersten erfolgreichen Refresh aufgerufen."""
        from homeassistant.helpers.event import async_track_time_interval

        # Analytics-Store laden
        self._store = Store(
            self.hass,
            ANALYTICS_STORAGE_VERSION,
            f"{ANALYTICS_STORAGE_KEY_PREFIX}{self.config_entry.entry_id}",
        )
        stored = await self._store.async_load()
        self._analytics = KWLAnalytics.from_dict(stored)
        _LOGGER.debug(
            "KWL Flex Analytics geladen – Reifegrad %.1f%%",
            self._analytics.analytics_maturity_pct,
        )

        # Periodischer Analytics-Speicher alle 30 Minuten
        async def _save_analytics(_now: Any = None) -> None:
            if self._analytics and self._store:
                await self._store.async_save(self._analytics.to_dict())

        self.config_entry.async_on_unload(
            async_track_time_interval(
                self.hass, _save_analytics, timedelta(minutes=30)
            )
        )

        # Initiale Zeitsynchronisation + geplante Wiederholung.
        # Cleanup einheitlich über async_on_unload (wie der Analytics-Timer),
        # damit nicht zwei verschiedene Teardown-Mechanismen parallel laufen.
        await self._async_sync_time()
        self.config_entry.async_on_unload(
            async_track_time_interval(
                self.hass,
                self._async_sync_time_callback,
                TIME_SYNC_INTERVAL,
            )
        )

    def async_teardown(self) -> None:
        """Freigabe von Ressourcen beim Entladen des Entries.

        Timer werden über async_on_unload automatisch abgemeldet -- hier nur
        noch die Modbus-Verbindung schließen.
        """
        if self._client.connected:
            self._client.close()

    @property
    def model_slug(self) -> str:
        """Modell-Slug für Entity-ID-Generierung (z.B. 'profi_air_360_flex')."""
        if self.capabilities:
            return self.capabilities.model
        return "profi_air_flex"

    @property
    def analytics(self) -> KWLAnalytics | None:
        return self._analytics

    # ── Interner Update-Zyklus ────────────────────────────────────────────────

    async def _async_update_data(self) -> KWLFlexData:
        """Liest alle relevanten Register und baut KWLFlexData."""
        async with self._lock:
            # Verbindung herstellen / wiederherstellen
            if self._needs_reconnect or not self._client.connected:
                await self._connect_and_init()

            try:
                raw = await self._read_all_registers()
            except (ModbusIOException, ConnectionError, OSError) as err:
                self._needs_reconnect = True
                raise UpdateFailed(
                    f"Modbus-Verbindung zu {self._host}:{self._port} unterbrochen: {err}"
                ) from err

        data = self._build_data(raw)
        self._handle_repair_issues(data)
        self._update_analytics(data)
        return data

    async def _connect_and_init(self) -> None:
        """Verbindet den Modbus-Client und liest einmalige Capabilities."""
        logging.getLogger("pymodbus").setLevel(logging.CRITICAL)
        if self._client.connected:
            self._client.close()
        await asyncio.sleep(0.1)  # kurze Pause vor Reconnect
        connected = await self._client.connect()
        if not connected:
            raise UpdateFailed(
                f"Modbus TCP Verbindung zu {self._host}:{self._port} fehlgeschlagen"
            )
        self._needs_reconnect = False

        # Capabilities beim ersten Verbinden laden
        if self.capabilities is None:
            await self._read_capabilities()

    async def _read_capabilities(self) -> None:
        """Liest einmalige Gerätedaten und befüllt self.capabilities + device_info."""
        raw: dict[str, list[int]] = {}
        for offset, count in _SETUP_BLOCKS:
            result = await self._client.read_holding_registers(
                address=offset, count=count, device_id=1
            )
            if result.isError():
                raise UpdateFailed(f"Setup-Read offset={offset} fehlgeschlagen")
            # Härtung: kurze Registerliste ohne isError() würde unten zu einem
            # IndexError/struct.error führen -- hier sauber als UpdateFailed
            # behandeln, damit HA das Setup korrekt erneut versucht.
            if len(result.registers) != count:
                raise UpdateFailed(
                    f"Setup-Read offset={offset}: erwartet {count} Register, "
                    f"erhalten {len(result.registers)}"
                )
            raw[f"s_{offset}"] = list(result.registers)

        u32 = self._decode_uint32

        # System-ID → Unit-Typ (Byte 0 des Low-Words)
        sys_id = u32(raw["s_2"])
        unit_type = sys_id & 0xFF
        model = UNIT_TYPE_TO_MODEL.get(unit_type)
        if model is None:
            raise UpdateFailed(
                f"Unbekannter UVC-Gerätetyp: {unit_type} "
                f"(unterstützt: {list(UNIT_TYPE_TO_MODEL.keys())})"
            )

        # Firmware-Version
        fw_raw = u32(raw["s_24"])
        fw_major = (fw_raw >> 8) & 0xFF
        fw_minor = fw_raw & 0xFF
        fw_str = f"{fw_major}.{fw_minor}"

        # MAC-Adresse → Unique-ID
        mac_high = u32(raw["s_40"][0:2])
        mac_low  = u32(raw["s_40"][2:4])
        mac_id   = f"{mac_high:08X}{mac_low:08X}"

        # A/B-Schalterstellung → Fan-Zuordnung
        # HALLeft=1 → Schalter in B-Position, HALRight=1 → Schalter in A-Position
        hal_left  = u32(raw["s_84"][0:2])
        hal_right = u32(raw["s_84"][2:4])
        # A-Position (HALRight=1): Fan1 = Zuluft, Fan2 = Abluft → fan1_is_extract=False
        # B-Position (HALLeft=1):  Fan1 = Abluft, Fan2 = Zuluft → fan1_is_extract=True
        fan1_is_extract = bool(hal_left)

        # Referenz-RPM bei Stufe 3
        ref_rpm_extract = u32(raw["s_518"][0:2])
        ref_rpm_supply  = u32(raw["s_518"][2:4])

        model_name = MODEL_DISPLAY.get(model, model)

        self.capabilities = KWLFlexCapabilities(
            model=model,
            mac_id=mac_id,
            firmware_version=fw_str,
            fan1_is_extract=fan1_is_extract,
            ref_rpm_extract_s3=ref_rpm_extract,
            ref_rpm_supply_s3=ref_rpm_supply,
        )

        # DeviceInfo mit bekannter MAC + Firmware aktualisieren.
        # Kein configuration_url: flex/flat-Geräte haben kein Web-Interface,
        # ein "modbus://"-Link wäre im Geräte-Dialog nicht öffnenbar (toter Link).
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, mac_id)},
            name=model_name,
            manufacturer="Fränkische Rohrwerke",
            model=model_name,
            sw_version=fw_str,
        )

        switch_pos = "B" if fan1_is_extract else "A"
        _LOGGER.info(
            "KWL Flex: %s erkannt (FW %s, Schalter %s, Ref-RPM Ex/Su %d/%d)",
            model_name, fw_str, switch_pos,
            ref_rpm_extract, ref_rpm_supply,
        )

    async def _read_all_registers(self) -> dict[str, list[int]]:
        """Liest Fast- und (alle 10 Polls) Slow-Register."""
        self._poll_count = (self._poll_count + 1) % _POLL_SLOW_DIVISOR
        raw: dict[str, list[int]] = {}

        # Fast-Blocks (jeder Poll)
        for offset, count in _FAST_BLOCKS:
            result = await self._client.read_holding_registers(
                address=offset, count=count, device_id=1
            )
            if result.isError():
                raise ModbusIOException(f"Read offset={offset} count={count} fehlgeschlagen")
            # Härtung: manche pymodbus-Transportfehler liefern eine zu kurze
            # Registerliste OHNE isError()=True. Ungeprüft würde das später in
            # _build_data zu einem struct.error/IndexError außerhalb der
            # Fehlerbehandlung führen und den gesamten Poll-Zyklus abbrechen.
            if len(result.registers) != count:
                raise ModbusIOException(
                    f"Read offset={offset}: erwartet {count} Register, "
                    f"erhalten {len(result.registers)}"
                )
            raw[f"f_{offset}"] = list(result.registers)

        # Slow-Blocks (jeder 10. Poll oder beim ersten Poll)
        if self._poll_count == 0 or self._slow_cache is None:
            slow: dict[str, list[int]] = {}
            for offset, count in _SLOW_BLOCKS:
                result = await self._client.read_holding_registers(
                    address=offset, count=count, device_id=1
                )
                if result.isError() or len(result.registers) != count:
                    _LOGGER.warning(
                        "Slow-Block offset=%d nicht (vollständig) lesbar – verwende Cache",
                        offset,
                    )
                else:
                    slow[f"sl_{offset}"] = list(result.registers)
            if slow:
                self._slow_cache = slow

        if self._slow_cache:
            raw.update(self._slow_cache)

        return raw

    # ── Daten-Dekodierung ─────────────────────────────────────────────────────

    @staticmethod
    def _decode_uint32(regs: list[int]) -> int:
        """Dekodiert 2 Register als UINT32 (Low-Register zuerst)."""
        from typing import cast as _cast
        return _cast(int, ModbusClientMixin.convert_from_registers(
            regs[:2], ModbusClientMixin.DATATYPE.UINT32, "little"
        ))

    @staticmethod
    def _decode_float(regs: list[int]) -> float:
        """Dekodiert 2 Register als FLOAT32 (CDAB Byte-Order → word_order='little')."""
        from typing import cast as _cast
        return _cast(float, ModbusClientMixin.convert_from_registers(
            regs[:2], ModbusClientMixin.DATATYPE.FLOAT32, "little"
        ))

    def _build_data(self, raw: dict[str, list[int]]) -> KWLFlexData:
        """Baut KWLFlexData aus den rohen Register-Listen."""
        caps = self.capabilities
        fan1_is_extract = caps.fan1_is_extract if caps else False

        u32 = self._decode_uint32
        flt = self._decode_float

        # Fan RPMs (Fast-Block 100, 4 Register)
        f100 = raw.get("f_100", [0, 0, 0, 0])
        fan1_rpm = flt(f100[0:2])
        fan2_rpm = flt(f100[2:4])

        # Temperaturen T1–T5 (Fast-Block 132, 10 Register)
        f132 = raw.get("f_132", [0] * 10)

        def _safe_temp(regs: list[int]) -> float | None:
            v = flt(regs)
            return v if -50.0 < v < 100.0 else None

        t1 = _safe_temp(f132[0:2])
        t2 = _safe_temp(f132[2:4])
        t3 = _safe_temp(f132[4:6])
        t4 = _safe_temp(f132[6:8])
        t5_raw = _safe_temp(f132[8:10])
        t5 = t5_raw if (t5_raw is not None and t5_raw != 0.0) else None

        # Vorheizer (Fast-Block 160)
        preheater_duty = int(u32(raw.get("f_160", [0, 0]))) & 0xFF

        # RH + Bypass (Fast-Block 196)
        f196 = raw.get("f_196", [0, 0, 0, 0])
        rh_raw    = int(u32(f196[0:2]))
        bypass_raw = int(u32(f196[2:4]))

        # Lüftungsstufe (Fast-Block 324)
        level = int(u32(raw.get("f_324", [0, 0])))
        level = max(1, min(4, level)) if 1 <= level <= 4 else 1

        # VOC (Fast-Block 430)
        voc_raw = int(u32(raw.get("f_430", [0, 0])))

        # Betriebsmodus (Fast-Block 472)
        mode = int(u32(raw.get("f_472", [0, 0])))

        # Alarm-Code (Fast-Block 516)
        alarm = int(u32(raw.get("f_516", [0, 0]))) & 0xFF

        # CO2 (Fast-Block 574)
        co2_raw = int(u32(raw.get("f_574", [0, 0])))

        # ── Slow-Block-Daten ──────────────────────────────────────────────────

        # RH-Sollwert (Slow-Block 340)
        rh_setpoint_raw = int(u32(raw.get("sl_340", [0, 0]))) if "sl_340" in raw else None

        # Bypass Tmin/Tmax (Slow-Block 444)
        sl444 = raw.get("sl_444")
        bypass_tmin = flt(sl444[0:2]) if sl444 else None
        bypass_tmax = flt(sl444[2:4]) if sl444 else None
        bypass_tmin = bypass_tmin if (bypass_tmin is not None and -20.0 < bypass_tmin < 30.0) else None
        bypass_tmax = bypass_tmax if (bypass_tmax is not None and  10.0 < bypass_tmax < 40.0) else None

        # Filter (Slow-Block 554)
        sl554 = raw.get("sl_554")
        filter_remaining = int(u32(sl554[0:2])) if sl554 else None
        filter_total     = int(u32(sl554[2:4])) if sl554 else None

        # Betriebsstunden (Slow-Block 624)
        hours = int(u32(raw.get("sl_624", [0, 0]))) if "sl_624" in raw else None

        return KWLFlexData(
            fan1_rpm=fan1_rpm,
            fan2_rpm=fan2_rpm,
            fan1_is_extract=fan1_is_extract,
            t1=t1, t2=t2, t3=t3, t4=t4, t5=t5,
            current_level=level,
            current_mode=mode,
            preheater_duty_pct=preheater_duty,
            bypass_state_raw=bypass_raw,
            alarm_code=alarm,
            rh_percent=rh_raw if rh_raw > 0 else None,
            rh_setpoint=rh_setpoint_raw if (rh_setpoint_raw and rh_setpoint_raw > 0) else None,
            voc_ppm=voc_raw if voc_raw > 0 else None,
            co2_ppm=co2_raw if co2_raw > 0 else None,
            bypass_tmin=bypass_tmin,
            bypass_tmax=bypass_tmax,
            filter_residual_days=filter_remaining,
            filter_total_days=filter_total,
            hours_total=hours,
            watt_map=self.watt_map,
            ref_rpm_extract_s3=caps.ref_rpm_extract_s3 if caps else None,
            ref_rpm_supply_s3=caps.ref_rpm_supply_s3 if caps else None,
        )

    # ── Analytics + Repair Issues ──────────────────────────────────────────────

    def _update_analytics(self, data: KWLFlexData) -> None:
        if self._analytics is None:
            return
        scan_s = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        snap = KWLPollSnapshot(
            timestamp=_time.time(),
            temp_abluft=data.temp_abluft,
            temp_zuluft=data.temp_zuluft,
            temp_aussenluft=data.temp_aussenluft,
            temp_fortluft=data.temp_fortluft,
            rpm_abluft=data.motor_abluft_rpm,
            rpm_zuluft=data.motor_zuluft_rpm,
            current_level=data.current_level,
            bypass_status=data.bypass_status,
            fan_at_level_4=(data.current_level == 4),
        )
        self._analytics.update(snap, poll_interval_s=float(scan_s))

    def _handle_repair_issues(self, data: KWLFlexData) -> None:
        """Erstellt/löscht Repair Issues nach _DEFECT_THRESHOLD aufeinanderfolgenden Polls."""
        # Bypass-Leckage
        if data.bypass_leaking:
            self._bypass_leak_count += 1
        else:
            self._bypass_leak_count = 0
            ir.async_delete_issue(self.hass, DOMAIN, "bypass_leaking")
        if self._bypass_leak_count >= _DEFECT_THRESHOLD:
            ir.async_create_issue(
                self.hass, DOMAIN, "bypass_leaking",
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="bypass_leaking",
            )

        # Motorasymmetrie
        if data.motor_asymmetry:
            self._motor_asym_count += 1
        else:
            self._motor_asym_count = 0
            ir.async_delete_issue(self.hass, DOMAIN, "motor_asymmetry")
        if self._motor_asym_count >= _DEFECT_THRESHOLD:
            ir.async_create_issue(
                self.hass, DOMAIN, "motor_asymmetry",
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="motor_asymmetry",
            )

        # Jahreswartung (Gesamt-Betriebsstunden)
        if (
            data.hours_total is not None
            and data.hours_total >= self._maintenance_next_threshold
        ):
            ir.async_create_issue(
                self.hass, DOMAIN, "annual_maintenance",
                is_fixable=True,
                severity=ir.IssueSeverity.WARNING,
                translation_key="annual_maintenance",
                data={"entry_id": self.config_entry.entry_id},
            )

    # ── Write-Methoden (Option C: jede Methode endet mit async_request_refresh) ─

    async def async_set_level(self, level: int) -> None:
        """Setzt die Lüftungsstufe (1–4).

        prmRomIdxSpeedLevel (Register 40325/40326) ist UINT32 — 2×16-Bit.
        FC06 (Write Single Register) kann nur ein 16-Bit-Wort schreiben und
        scheitert daher erwartungsgemäß (oberes Wort bliebe unverändert/0,
        Wert wäre ungültig). FC16 (Write Multiple Registers) schreibt beide
        Wörter atomar — exakt das Muster das _write_uint32() bereits für
        Modus, Filter-Reset, Alarm-Clear und Filter-Intervall verwendet.

        Das Gerät übernimmt Stufenänderungen laut Doku nur im Manual-Mode.
        Ist das Gerät in einem anderen Modus, wird automatisch auf Manual
        gewechselt — analog zu async_set_mode().
        """
        level = max(1, min(4, level))
        async with self._lock:
            if self.data is not None and self.data.current_mode_text != "Manuell":
                await self._write_uint32(168, FLEX_MODE_TO_WRITE["Manuell"])
                await asyncio.sleep(0.1)
            await self._write_uint32(324, level)  # offset 324 = 40325
        await self.async_request_refresh()  # Option C: sofortige Bestätigung

    async def async_set_mode(self, mode_name: str) -> None:
        """Setzt den Betriebsmodus (z.B. 'Manuell', 'Urlaub').

        Beendet ggf. den aktuellen Sondermodus (Urlaub, Sommer, Nacht, Kamin)
        bevor der neue Modus aktiviert wird.
        """
        write_mask = FLEX_MODE_TO_WRITE.get(mode_name)
        if write_mask is None:
            _LOGGER.error("Unbekannter Modus: %r", mode_name)
            return

        async with self._lock:
            # Aktuellen Modus lesen um ggf. End-Bitmask zu senden
            if self.data is not None:
                current_name = self.data.current_mode_text
                end_mask = FLEX_MODE_TO_END.get(current_name)
                if end_mask is not None:
                    await self._write_uint32(168, end_mask)  # offset 168 = 40169
                    await asyncio.sleep(0.1)
            await self._write_uint32(168, write_mask)

        await self.async_request_refresh()  # Option C: sofortige Bestätigung

    async def async_reset_filter(self) -> None:
        """Setzt den Filter-Timer zurück (schreibt 1 auf Register 40559)."""
        async with self._lock:
            await self._write_uint32(558, 1)  # offset 558 = 40559
        await self.async_request_refresh()

    async def async_clear_alarm(self) -> None:
        """Löscht den aktiven Alarm (schreibt 0 auf Register 40515)."""
        async with self._lock:
            await self._write_uint32(514, 0)  # offset 514 = 40515
        await self.async_request_refresh()

    async def async_set_filter_total(self, days: int) -> None:
        """Setzt das Filterintervall in Tagen (Register 40557)."""
        days = max(30, min(360, days))
        async with self._lock:
            await self._write_uint32(556, days)  # offset 556 = 40557
        await self.async_request_refresh()

    async def async_reset_analytics(self) -> None:
        """Setzt die Analytics-Baselines zurück (nach Filterwechsel)."""
        if self._analytics is not None:
            self._analytics.reset_baselines()
            if self._store is not None:
                await self._store.async_save(self._analytics.to_dict())
        # Wartungsgrenze vorwärts setzen
        if self.data and self.data.hours_total is not None:
            new_threshold = self.data.hours_total + ANNUAL_MAINTENANCE_HOURS
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={**self.config_entry.data, "maintenance_next_threshold": new_threshold},
            )
            self._maintenance_next_threshold = new_threshold
            ir.async_delete_issue(self.hass, DOMAIN, "annual_maintenance")

    # ── Hilfsmethoden ─────────────────────────────────────────────────────────

    async def _write_uint32(self, offset: int, value: int) -> None:
        """Schreibt einen UINT32-Wert via FC16 (2 Register, Low-first)."""
        regs = ModbusClientMixin.convert_to_registers(
            value, ModbusClientMixin.DATATYPE.UINT32, "little"
        )
        result = await self._client.write_registers(
            address=offset, values=regs, device_id=1
        )
        if result.isError():
            raise ModbusIOException(f"Write-Fehler: offset={offset}, value={value}")

    async def _async_sync_time(self, _now: Any = None) -> None:
        """Synchronisiert die Geräteuhrzeit (Unix-Timestamp → Register 40111)."""
        try:
            async with self._lock:
                if not self._client.connected:
                    return
                await self._write_uint32(110, int(_time.time()))  # offset 110 = 40111
            if self._time_sync_failures:
                _LOGGER.info(
                    "KWL Flex: Zeitsynchronisation wieder erfolgreich nach %d Fehlversuchen",
                    self._time_sync_failures,
                )
            self._time_sync_failures = 0
            _LOGGER.debug("KWL Flex: Zeitsynchronisation durchgeführt")
        except Exception as err:
            # Erste Warnung sichtbar, danach auf debug drosseln -- sonst flutet
            # ein dauerhaft nicht erreichbares Gerät das Log im Sync-Intervall.
            self._time_sync_failures += 1
            if self._time_sync_failures == 1:
                _LOGGER.warning("KWL Flex: Zeitsynchronisation fehlgeschlagen: %s", err)
            else:
                _LOGGER.debug(
                    "KWL Flex: Zeitsynchronisation weiterhin fehlgeschlagen (#%d): %s",
                    self._time_sync_failures, err,
                )

    async def _async_sync_time_callback(self, _now: Any = None) -> None:
        await self._async_sync_time()

    # ── Hilfsmethode: Watt-Map aufbauen ──────────────────────────────────────

    @staticmethod
    def _build_watt_map(entry: ConfigEntry) -> dict[int, float | None]:
        """Liest Watt-Werte aus Options/Data; None wenn nicht konfiguriert."""
        model = entry.data.get("model", MODEL_PROFI_AIR_360_FLEX)
        defaults = WATT_DEFAULTS.get(model, {1: None, 2: None, 3: None, 4: None})
        return {
            1: entry.options.get(CONF_WATT_LEVEL_1, entry.data.get(CONF_WATT_LEVEL_1, defaults.get(1))),
            2: entry.options.get(CONF_WATT_LEVEL_2, entry.data.get(CONF_WATT_LEVEL_2, defaults.get(2))),
            3: entry.options.get(CONF_WATT_LEVEL_3, entry.data.get(CONF_WATT_LEVEL_3, defaults.get(3))),
            4: entry.options.get(CONF_WATT_LEVEL_4, entry.data.get(CONF_WATT_LEVEL_4, defaults.get(4))),
        }

    # ─────────────────────────────────────────────────────────────────────────
