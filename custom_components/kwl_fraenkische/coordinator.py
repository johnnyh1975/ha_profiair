"""DataUpdateCoordinator fuer die Fraenkische Rohrwerke KWL-Integration."""
from __future__ import annotations

import asyncio
from typing import Any, Protocol
import logging
from dataclasses import dataclass
from datetime import timedelta
from xml.etree import ElementTree

import aiohttp
from homeassistant.helpers import issue_registry as ir
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .analytics import (
    ANALYTICS_STORAGE_KEY_PREFIX,
    ANALYTICS_STORAGE_VERSION,
    KWLAnalytics,
    KWLPollSnapshot,
)

from .const import (
    ALL_KNOWN_TAGS,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    ENDPOINT_INSTALL,
    ENDPOINT_TIME,
    ENDPOINT_WOPLA,
    REQUIRED_XML_TAGS,
)

_LOGGER = logging.getLogger(__name__)

# ── KWLCapabilities ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class KWLCapabilities:
    """Erkannte Faehigkeiten der KWL -- ermittelt beim ersten Poll."""

    available_tags: frozenset[str]
    unknown_tags: frozenset[str]
    reachable_endpoints: frozenset[str]

    @property
    def has_motor_sensors(self) -> bool:
        return "MoStZlUm" in self.available_tags

    @property
    def has_airflow_voltage(self) -> bool:
        return "st1z" in self.available_tags

    @property
    def has_temp_corrections(self) -> bool:
        return "kor1" in self.available_tags

    @property
    def has_ext_sensors(self) -> bool:
        return "sensortyp1" in self.available_tags

    @property
    def has_filter_lifetime(self) -> bool:
        return "rest_time" in self.available_tags

    @property
    def has_operating_hours(self) -> bool:
        return "BsSt1" in self.available_tags

    @property
    def has_safety_manager(self) -> bool:
        return "safety" in self.available_tags

    @property
    def has_preheater(self) -> bool:
        return "vorheiz" in self.available_tags

    @property
    def has_language_select(self) -> bool:
        return "SprachWahl" in self.available_tags

    @property
    def has_installer_access(self) -> bool:
        return ENDPOINT_INSTALL in self.reachable_endpoints

    @property
    def has_time_sync(self) -> bool:
        return ENDPOINT_TIME in self.reachable_endpoints

    @property
    def has_program_control(self) -> bool:
        return ENDPOINT_WOPLA in self.reachable_endpoints

    def summary(self) -> str:
        parts = []
        if self.has_motor_sensors: parts.append("Motor-Diagnostik")
        if self.has_airflow_voltage: parts.append("Airflow-Kalibrierung")
        if self.has_temp_corrections: parts.append("Temp-Korrekturen")
        if self.has_ext_sensors: parts.append("Ext.Sensoren")
        if self.has_filter_lifetime: parts.append("Filter-Restlaufzeit")
        if self.has_installer_access: parts.append("Installer")
        if self.has_time_sync: parts.append("Zeitsync")
        if self.has_program_control: parts.append("Wochenplan")
        return (
            f"{len(parts)} Features: {', '.join(parts)}"
            + (f" | {len(self.unknown_tags)} unbekannte Tags" if self.unknown_tags else "")
        )


class _SupportedDesc(Protocol):
    required_tag: str | None
    required_endpoint: str | None


def _is_supported(desc: _SupportedDesc, caps: KWLCapabilities) -> bool:
    """True wenn EntityDescription von dieser Firmware unterstuetzt wird."""
    if desc.required_tag and desc.required_tag not in caps.available_tags:
        return False
    if desc.required_endpoint and desc.required_endpoint not in caps.reachable_endpoints:
        return False
    return True



# SCAN_INTERVAL wird nicht mehr direkt genutzt -- Wert kommt aus entry.options
# Default: DEFAULT_SCAN_INTERVAL aus const.py
TIME_SYNC_INTERVAL = timedelta(hours=24)
ANNUAL_MAINTENANCE_HOURS = 8760  # 1 Jahr in Stunden


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value.strip())
    except (ValueError, AttributeError):
        return None


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return None


def _parse_volt(value: str | None) -> float | None:
    """XML liefert Volt * 10 als Ganzzahl (z.B. 24 = 2.4 V)."""
    raw = _parse_int(value)
    if raw is None:
        return None
    return round(raw / 10, 1)


def _parse_korrektur(value: str | None) -> float | None:
    """Temperaturkorrektur: XML liefert Integer * 10 (z.B. 5 = 0.5 C)."""
    raw = _parse_int(value)
    if raw is None:
        return None
    return round(raw / 10, 1)


def _build_time_payload(now: Any) -> dict[str, str]:
    """Baut den timesubmit-String nach dem Geraete-Format auf.

    Format: J{JJ}M{MM}T{TT}W{W}h{hh}m{mm}s{ss}
    Wochentag: 0=So, 1=Mo ... 6=Sa  (identisch mit Python's weekday()+1 % 7)
    Das Geraet erwartet den JS-Wochentag: 0=Sonntag, 1=Montag ... 6=Samstag.
    """
    year = now.year % 100
    month = now.month
    day = now.day
    # Python: weekday() 0=Mo..6=So -> JS: 1=Mo..6=Sa, 0=So
    js_weekday = now.weekday() + 1 if now.weekday() < 6 else 0
    hour = now.hour
    minute = now.minute
    second = now.second

    time_str = (
        f"J{year:02d}"
        f"M{month:02d}"
        f"T{day:02d}"
        f"W{js_weekday}"
        f"h{hour:02d}"
        f"m{minute:02d}"
        f"s{second:02d}"
    )
    return {"timesubmit": time_str}


def _build_dst_payload(now: Any) -> dict[str, str]:
    """Bestimmt ob Sommerzeit aktiv ist und gibt den passenden POST-Wert zurueck."""
    # dst_offset > 0 bedeutet Sommerzeit aktiv
    is_dst = bool(now.dst() and now.dst().total_seconds() > 0)
    return {"SoZeit": "soze1" if is_dst else "soze0"}


class KWLData:
    """Geparste und normalisierte Daten aus status.xml."""

    def __init__(self, raw: dict[str, str]) -> None:
        self._raw = raw

    @property
    def current_level(self) -> int:
        for level in (1, 2, 3, 4):
            if self._raw.get(f"stufe{level}", "0").strip() == "1":
                return level
        return 1

    @property
    def current_level_text(self) -> str:
        return self._raw.get("aktuell0", "").strip()

    @property
    def temp_abluft(self) -> float | None:
        return _parse_float(self._raw.get("abl0"))

    @property
    def temp_zuluft(self) -> float | None:
        return _parse_float(self._raw.get("zul0"))

    @property
    def temp_aussenluft(self) -> float | None:
        return _parse_float(self._raw.get("aul0"))

    @property
    def temp_fortluft(self) -> float | None:
        return _parse_float(self._raw.get("fol0"))

    @property
    def bypass_threshold_aul(self) -> float | None:
        return _parse_float(self._raw.get("BipaAutAUL"))

    @property
    def bypass_threshold_abl(self) -> float | None:
        return _parse_float(self._raw.get("BipaAutABL"))

    @property
    def korrektur_abluft(self) -> float | None:
        return _parse_korrektur(self._raw.get("kor1"))

    @property
    def korrektur_zuluft(self) -> float | None:
        return _parse_korrektur(self._raw.get("kor2"))

    @property
    def korrektur_fortluft(self) -> float | None:
        return _parse_korrektur(self._raw.get("kor3"))

    @property
    def korrektur_aussenluft(self) -> float | None:
        return _parse_korrektur(self._raw.get("kor4"))

    @property
    def motor_zuluft_rpm(self) -> int | None:
        return _parse_int(self._raw.get("MoStZlUm"))

    @property
    def motor_zuluft_volt(self) -> float | None:
        return _parse_volt(self._raw.get("MoStZlVo"))

    @property
    def motor_abluft_rpm(self) -> int | None:
        return _parse_int(self._raw.get("MoStAlUm"))

    @property
    def motor_abluft_volt(self) -> float | None:
        return _parse_volt(self._raw.get("MoStAlVo"))

    @property
    def airflow_s1_supply(self) -> float | None:
        return _parse_volt(self._raw.get("st1z"))

    @property
    def airflow_s1_exhaust(self) -> float | None:
        return _parse_volt(self._raw.get("st1a"))

    @property
    def airflow_s2_supply(self) -> float | None:
        return _parse_volt(self._raw.get("st2z"))

    @property
    def airflow_s2_exhaust(self) -> float | None:
        return _parse_volt(self._raw.get("st2a"))

    @property
    def airflow_s3_supply(self) -> float | None:
        return _parse_volt(self._raw.get("st3z"))

    @property
    def airflow_s3_exhaust(self) -> float | None:
        return _parse_volt(self._raw.get("st3a"))

    @property
    def airflow_s4_supply(self) -> float | None:
        return _parse_volt(self._raw.get("st4z"))

    @property
    def airflow_s4_exhaust(self) -> float | None:
        return _parse_volt(self._raw.get("st4a"))

    @property
    def hours_level_1(self) -> int | None:
        return _parse_int(self._raw.get("BsSt1"))

    @property
    def hours_level_2(self) -> int | None:
        return _parse_int(self._raw.get("BsSt2"))

    @property
    def hours_level_3(self) -> int | None:
        return _parse_int(self._raw.get("BsSt3"))

    @property
    def hours_level_4(self) -> int | None:
        return _parse_int(self._raw.get("BsSt4"))

    @property
    def hours_frost(self) -> int | None:
        """Betriebsstunden Frostschutz in Stunden (BsFs).
        Laut install.htm HTML wird 'h' als Einheit angezeigt -- korrekt als Stunden.
        """
        return _parse_int(self._raw.get("BsFs"))

    @property
    def hours_preheater(self) -> int | None:
        return _parse_int(self._raw.get("BsVhr"))

    @property
    def filter_total_days(self) -> int | None:
        """Gesamtlaufzeit bis Filtertausch in Tagen (filtertime)."""
        return _parse_int(self._raw.get("filtertime"))

    @property
    def filter_residual_days(self) -> int | None:
        """Verbleibende Tage bis Filtertausch (rest_time)."""
        return _parse_int(self._raw.get("rest_time"))

    @property
    def language(self) -> str | None:
        """Aktuelle Spracheinstellung (SprachWahl)."""
        v = self._raw.get("SprachWahl", "")
        return v.strip() if v else None

    @property
    def program_control(self) -> str | None:
        """Programm- oder Handsteuerung (control0)."""
        v = self._raw.get("control0", "")
        return v.strip() if v else None

    # ── Digital Inputs ────────────────────────────────────────────────
    @property
    def digital_input_1(self) -> bool:
        return (self._raw.get("DiIn1", "Aus").strip().lower() == "ein")

    @property
    def digital_input_2(self) -> bool:
        return (self._raw.get("DiIn2", "Aus").strip().lower() == "ein")

    @property
    def digital_input_3(self) -> bool:
        return (self._raw.get("DiIn3", "Aus").strip().lower() == "ein")


    @property
    def bypass_status(self) -> str:
        return self._raw.get("bypass", "").strip()

    # ── Derived / Diagnostic Properties ─────────────────────────────────

    @property
    def heat_recovery_efficiency(self) -> float | None:
        """Waermerueckgewinnungsgrad eta in Prozent.

        eta = (T_zuluft - T_aussen) / (T_abluft - T_aussen) * 100

        Typisch: 75-85% bei sauberer Anlage.
        Unter 65% dauerhaft: Filter oder Waermetauscher reinigen.
        Nur sinnvoll wenn T_abluft - T_aussen >= 3 K (sonst Messrauschen dominiert).
        Typisch: 75-87% im Heizbetrieb (Bypass zu, grosses Delta).
        Im Sommer (Bypass offen, kleines Delta) 40-65% -- das ist normal.
        Herstellerwert ηt = 87% bei Nennbetrieb und ausgeglichenem Volumenstrom.
        """
        t_ab = self.temp_abluft
        t_zu = self.temp_zuluft
        t_au = self.temp_aussenluft
        if t_ab is None or t_zu is None or t_au is None:
            return None
        delta = t_ab - t_au
        if delta < 3.0:
            return None  # < 3 K: Messrauschen macht Berechnung unzuverlaessig
        return round((t_zu - t_au) / delta * 100, 1)

    @property
    def heat_recovery_watts(self) -> float | None:
        """Zurueckgewonnene Waermeleistung in Watt.

        Q = 0.34 [Wh/(m³·K)] × Volumenstrom [m³/h] × (T_abluft − T_zuluft) [K]

        Volumenstrom wird dynamisch aus der Motordrehzahl abgeleitet wenn verfügbar
        (Fanlaufgesetz Q ∝ n, verankert am Bezugs-Volumenstrom des Herstellers).
        Fallback: modellspezifische Stufen-Tabelle aus Fanlaufgesetz-Berechnung.

        Genauigkeit: ±15 % typisch; genaue Messung erfordert Volumenstromsensor.
        """
        t_ab = self.temp_abluft
        t_zu = self.temp_zuluft
        if t_ab is None or t_zu is None:
            return None
        delta = t_ab - t_zu
        if delta <= 0:
            return None

        # Dynamische Berechnung aus Motordrehzahl (bevorzugt)
        rpm_ab = self.motor_abluft_rpm
        if rpm_ab is not None and rpm_ab > 100:
            # Standardreferenz: 400 touch Bezugs-Volumenstrom 280 m³/h @ RPM_ref 2085
            # Gültig für Installationen mit ähnlichem Druckverlust (10-50 Pa)
            q_ref, rpm_ref = 280.0, 2085.0
            volumenstrom = q_ref * rpm_ab / rpm_ref
        else:
            # Fallback: statische Tabelle (fan-law abgeleitet, 400-touch-Referenz)
            volumenstrom = {1: 115, 2: 169, 3: 263, 4: 341}.get(self.current_level, 263)

        return round(0.34 * volumenstrom * delta, 0)

    @property
    def frost_risk(self) -> bool:
        """True wenn Frost-Risiko fuer den Waermetauscher besteht.

        Kriterium: Aussenluft < -5 C UND Zuluft < 5 C.
        """
        t_au = self.temp_aussenluft
        t_zu = self.temp_zuluft
        if t_au is None or t_zu is None:
            return False
        return t_au < -5.0 and t_zu < 5.0

    @property
    def bypass_leaking(self) -> bool:
        """True wenn Bypass-Leckage vermutet wird.

        Zwei Erkennungspfade:

        Heizbetrieb (T_abluft - T_aussen >= 5 K, Bypass soll zu sein):
          Fortlufttemperatur fast identisch mit Aussenluft (< 4 K Abstand)
          obwohl der Bypass geschlossen sein soll.

        Sommerbetrieb (T_abluft - T_aussen 2-5 K, Bypass explizit zu):
          Bypass ist auf "zu" gesetzt, aber Fortluft folgt Aussenluft
          innerhalb 2 K -- deutet auf undichte Bypass-Klappe hin.
          Schwaechere Schwelle, aber durch _DEFECT_THRESHOLD (10 Polls) abgesichert.
        """
        if "offen" in self.bypass_status.lower():
            return False  # Bypass soll offen sein -- kein Defekt
        t_fort = self.temp_fortluft
        t_au = self.temp_aussenluft
        t_ab = self.temp_abluft
        if t_fort is None or t_au is None or t_ab is None:
            return False
        delta = t_ab - t_au
        # Heizbetrieb: strenge Bedingung
        if delta >= 5.0:
            return abs(t_fort - t_au) < 4.0
        # Sommerbetrieb: softer, aber nur wenn Bypass explizit geschlossen
        if 2.0 <= delta < 5.0 and "zu" in self.bypass_status.lower():
            return abs(t_fort - t_au) < 2.0
        return False

    @property
    def motor_asymmetry(self) -> bool:
        """True wenn Motorasymmetrie > 22% erkannt wird.

        Zuluftmotor laeuft konstruktionsbedingt ~20% schneller als Abluftmotor
        (leichter Ueberdruck im Gebaeudeinneren -- normaler Auslegungswert).
        Eine Asymmetrie > 22% deutet auf Motorverschleiss oder einseitig
        verstopften Filter hin.

        Zusaetzlich: wenn Abluft schneller als Zuluft dreht (umgekehrter Druck),
        wird das als Defekt gewertet unabhaengig vom Prozentwert.
        Schwellenwert: 10% -- gibt Rausch-Toleranz.

        Fuer Trend-Erkennung (fruehwarnung) siehe analytics.ratio_anomaly.
        """
        rpm_zu = self.motor_zuluft_rpm
        rpm_ab = self.motor_abluft_rpm
        if rpm_zu is None or rpm_ab is None or max(rpm_zu, rpm_ab) == 0:
            return False
        # Umgekehrte Asymmetrie: Abluft schneller als Zuluft
        if rpm_ab > rpm_zu * 1.10:
            return True
        # Zu grosse Asymmetrie in erwarteter Richtung
        asymmetrie = abs(rpm_zu - rpm_ab) / max(rpm_zu, rpm_ab)
        return asymmetrie > 0.22

    @property
    def bypass_recommended(self) -> bool:
        """True wenn Bypass-Vorkuehlung gerade sinnvoll waere.

        Kriterium: Aussenluft mindestens 3 K kuehler als Abluft
        UND Abluft > 22 C (Haus warm genug zum Vorkuehlen)
        UND Aussenluft > 10 C (kein Frost-Risiko).

        Schwelle 3 K entspricht dem empfohlenen bypass_delta_schwelle
        der Sommer-Kuehlungs-Automation.
        """
        t_au = self.temp_aussenluft
        t_ab = self.temp_abluft
        if t_au is None or t_ab is None:
            return False
        return (
            t_au < t_ab - 3.0
            and t_ab > 22.0
            and t_au > 10.0
        )

    @property
    def filter_ok(self) -> bool:
        return "ersetzt" in self._raw.get("filter0", "").strip().lower()

    @property
    def safety_active(self) -> bool:
        return "nicht aktiv" not in self._raw.get("safety", "").strip().lower()

    @property
    def passive_mode(self) -> bool:
        return self._raw.get("passiv", "").strip().lower() == "ein"

    @property
    def preheater_active(self) -> bool:
        return "aktiv" in self._raw.get("vorheiz", "").strip().lower()

    @property
    def install_type(self) -> str:
        return self._raw.get("installtyp", "").strip()

    @property
    def party_timer_minutes(self) -> int | None:
        return _parse_int(self._raw.get("partytime"))

    @property
    def nachlauf_minutes(self) -> int | None:
        return _parse_int(self._raw.get("nachlauf"))

    @property
    def system_message(self) -> str:
        return self._raw.get("meldung", "").strip()

    @property
    def base_level(self) -> str:
        return self._raw.get("grundst", "").strip()

    @property
    def ext_sensor_type_1(self) -> str:
        return self._raw.get("sensortyp1", "").strip()

    @property
    def ext_sensor_type_2(self) -> str:
        return self._raw.get("sensortyp2", "").strip()

    @property
    def ext_sensor_type_3(self) -> str:
        return self._raw.get("sensortyp3", "").strip()

    @property
    def ext_sensor_type_4(self) -> str:
        return self._raw.get("sensortyp4", "").strip()

    @property
    def ext_sensor_value_1(self) -> float | None:
        return _parse_float(self._raw.get("S1amb0"))

    @property
    def ext_sensor_value_2(self) -> float | None:
        return _parse_float(self._raw.get("S2amb0"))

    @property
    def ext_sensor_value_3(self) -> float | None:
        return _parse_float(self._raw.get("S3amb0"))

    @property
    def ext_sensor_value_4(self) -> float | None:
        return _parse_float(self._raw.get("S4amb0"))

    def raw(self, key: str) -> str | None:
        return self._raw.get(key)


class KWLCoordinator(DataUpdateCoordinator[KWLData]):
    """Koordiniert den periodischen Datenabruf und die Zeitsynchronisation."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        host: str,
        username: str,
        password: str,
        watt_map: dict[int, float] | None = None,
    ) -> None:
        self.host = host
        self._mac_id = entry.data.get("mac", host)
        self.watt_map: dict[int, float] = watt_map or {1: 11.0, 2: 17.5, 3: 43.5, 4: 80.0}
        self._install_auth = aiohttp.BasicAuth(username, password)
        self._status_url = f"http://{host}/status.xml"
        self._unsub_time_sync = None
        self.capabilities: KWLCapabilities | None = None
        self._bypass_leak_count: int = 0
        self._motor_asym_count: int = 0
        self._unknown_tags_logged: bool = False  # log once after discovery only
        # Analytics engine + persistent store
        self._analytics: KWLAnalytics | None = None
        self._store: Store | None = None
        # Naechste Wartungswarnung -- aus entry.data laden (nicht options, da sonst
        # options_update_listener einen ungewollten Reload ausloest)
        self._maintenance_next_threshold: float = entry.data.get(
            "maintenance_next_threshold", float(ANNUAL_MAINTENANCE_HOURS)
        )

        scan_seconds = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name="KWL Fraenkische Rohrwerke",
            update_interval=timedelta(seconds=scan_seconds),
            config_entry=entry,
        )
        # HA-verwaltete Session -- wird automatisch mit HA lifecycle verwaltet
        self._session = async_get_clientsession(hass)

        # Einheitliches Device-Info fuer alle Entities dieser Integration
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, self._mac_id)},
            name="KWL",
            manufacturer="Fraenkische Rohrwerke",
            model="Profi-Air",
            sw_version=None,
            configuration_url=f"http://{host}",
        )

    async def async_setup(self) -> None:
        """Wird nach dem ersten erfolgreichen Datenabruf aufgerufen.

        Startet die automatische Zeitsynchronisation und laedt die
        Analytics-Baselines aus dem persistenten Speicher.
        """
        # Analytics persistenter Speicher (pro Config Entry)
        self._store = Store(
            self.hass,
            ANALYTICS_STORAGE_VERSION,
            f"{ANALYTICS_STORAGE_KEY_PREFIX}{self.config_entry.entry_id}",
        )
        stored = await self._store.async_load()
        self._analytics = KWLAnalytics.from_dict(stored)
        _LOGGER.debug(
            "KWL Analytics geladen -- Reifegrad %.1f%%",
            self._analytics.analytics_maturity_pct,
        )

        await self._async_sync_time()

        self._unsub_time_sync = async_track_time_interval(
            self.hass,
            self._async_sync_time_callback,
            TIME_SYNC_INTERVAL,
        )
        _LOGGER.debug("KWL Zeitsynchronisation eingerichtet (alle 24h)")

    async def _async_sync_time_callback(self, _now: object = None) -> None:
        """Callback fuer den 24h-Timer."""
        await self._async_sync_time()

    async def _async_sync_time(self) -> None:
        """Sendet die aktuelle HA-Systemzeit und DST-Status an die KWL.

        Verwendet die HA-Zeitzone (dt_util.now()) damit Sommer-/Winterzeit
        korrekt aus der konfigurierten HA-Zeitzone abgeleitet wird.
        Wird uebersprungen wenn /time.htm nicht erreichbar ist.
        """
        if self.capabilities and not self.capabilities.has_time_sync:
            _LOGGER.debug("Zeitsync nicht verfuegbar -- Endpunkt nicht erreichbar")
            return
        now = dt_util.now()  # timezone-aware, in der HA-Zeitzone
        time_payload = _build_time_payload(now)
        dst_payload = _build_dst_payload(now)

        url = f"http://{self.host}/time.htm"
        try:
            session = self._get_session()
            # Erst Zeit senden
            async with session.post(
                url,
                data=time_payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                resp.raise_for_status()
            # Dann Sommer-/Winterzeit setzen
            async with session.post(
                url,
                data=dst_payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                resp.raise_for_status()

            _LOGGER.info(
                "KWL Zeitsynchronisation erfolgreich: %s (DST: %s)",
                now.strftime("%Y-%m-%d %H:%M:%S %Z"),
                "Sommer" if dst_payload["SoZeit"] == "soze1" else "Winter",
            )
        except aiohttp.ClientError as err:
            _LOGGER.warning("KWL Zeitsynchronisation fehlgeschlagen: %s", err)

    async def _discover_capabilities(self, raw: dict[str, str]) -> None:
        """Erkennt Capabilities der KWL beim ersten Poll."""
        available = frozenset(raw.keys())

        # Endpunkte parallel testen (Timeout je 3s)
        install_ok, time_ok, wopla_ok = await asyncio.gather(
            self._probe_endpoint(ENDPOINT_INSTALL),
            self._probe_endpoint(ENDPOINT_TIME),
            self._probe_endpoint(ENDPOINT_WOPLA),
        )
        reachable: set[str] = set()
        if install_ok: reachable.add(ENDPOINT_INSTALL)
        if time_ok:    reachable.add(ENDPOINT_TIME)
        if wopla_ok:   reachable.add(ENDPOINT_WOPLA)

        unknown = available - ALL_KNOWN_TAGS

        self.capabilities = KWLCapabilities(
            available_tags=available,
            unknown_tags=unknown,
            reachable_endpoints=frozenset(reachable),
        )
        _LOGGER.info("KWL Discovery abgeschlossen: %s", self.capabilities.summary())

    async def _probe_endpoint(self, path: str) -> bool:
        """Gibt True zurueck wenn Endpunkt existiert (nicht 404)."""
        try:
            url = f"http://{self.host}{path}"
            async with self._get_session().get(
                url, timeout=aiohttp.ClientTimeout(total=3)
            ) as resp:
                return resp.status != 404
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            return False

    def async_teardown(self) -> None:
        """Raeumt den Zeitsync-Listener auf beim Entladen der Integration."""
        if self._unsub_time_sync is not None:
            self._unsub_time_sync()
            self._unsub_time_sync = None


    async def _async_update_data(self) -> KWLData:
        try:
            session = self._get_session()
            async with session.get(
                self._status_url,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                resp.raise_for_status()
                text = await resp.text(encoding="utf-8", errors="replace")
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Verbindungsfehler zur KWL ({self.host}): {err}") from err

        try:
            raw = _parse_xml(text)
        except ElementTree.ParseError as err:
            raise UpdateFailed(f"Ungueltiges XML von der KWL: {err}") from err

        # Minimalvalidierung -- Pflicht-Tags muessen vorhanden sein
        missing = REQUIRED_XML_TAGS - frozenset(raw.keys())
        if missing:
            raise UpdateFailed(
                f"Unvollstaendige XML-Antwort vom Geraet -- fehlende Tags: {missing}"
            )

        data = KWLData(raw)

        # Repair Issue fuer Filterwechsel
        if not data.filter_ok:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                "filter_needs_replacement",
                is_fixable=True,
                severity=ir.IssueSeverity.WARNING,
                translation_key="filter_needs_replacement",
                data={"entry_id": self.config_entry.entry_id},
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, "filter_needs_replacement")

        # Repair Issue fuer Jahreswartung
        # _maintenance_acknowledged wird in repairs.py gesetzt wenn Nutzer quittiert
        # Verhindert dass das Issue nach Quittierung sofort wieder erscheint
        total_hours = sum(filter(None, [
            data.hours_level_1, data.hours_level_2,
            data.hours_level_3, data.hours_level_4,
        ]))
        if total_hours > self._maintenance_next_threshold:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                "annual_maintenance_due",
                is_fixable=True,
                severity=ir.IssueSeverity.WARNING,
                translation_key="annual_maintenance_due",
                data={"entry_id": self.config_entry.entry_id,
                      "hours": total_hours},
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, "annual_maintenance_due")

        # Repair Issues fuer Geraetedefekte -- erst nach 3 aufeinanderfolgenden Polls
        # verhindert Fehlalarme bei kurzen Messwertschwankungen (z.B. Motorstart)
        _DEFECT_THRESHOLD = 10  # 10 x 30s = 5 Minuten stabile Anomalie

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

        # Discovery beim ersten Poll
        if self.capabilities is None:
            await self._discover_capabilities(raw)

        # unknown_tags nur einmal nach Discovery loggen
        if (
            self.capabilities is not None
            and self.capabilities.unknown_tags
            and not self._unknown_tags_logged
        ):
            _LOGGER.info(
                "Unbekannte XML-Tags gefunden (neue Firmware?): %s -- "
                "Bitte GitHub Issue eroeffnen: https://github.com/johnnyh1975/ha_profiair400/issues",
                sorted(self.capabilities.unknown_tags),
            )
            self._unknown_tags_logged = True

        # Analytics aktualisieren und verzoegert persistieren (alle 30 min)
        if self._analytics is not None and self._store is not None:
            import time as _time
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
            self._store.async_delay_save(self._analytics.to_dict, 1800)

        return data

    def _get_session(self) -> aiohttp.ClientSession:
        """Gibt die HA-verwaltete aiohttp Session zurueck."""
        return self._session  # type: ignore[no-any-return]

    @property
    def analytics(self) -> KWLAnalytics | None:
        """Zugriff auf die Analytics-Engine fuer Entity-Lesezugriffe."""
        return self._analytics

    @property
    def rpm_reference_stufe4(self) -> float:
        """Referenz-RPM (Abluft) bei Stufe 4 fuer dynamische Leistungsberechnung.

        Nutzt die selbstkalibrierte Analytics-Baseline sobald MIN_N_RPM Samples
        vorliegen. Davor: Fallback aus gemessenen Installationsdaten (400 touch,
        st4a = 6.5 V → 2538 RPM).
        """
        if self._analytics is not None:
            baseline = self._analytics.rpm_level_baseline(4)
            if baseline is not None:
                return baseline
        return 2538.0  # gemessener Standardwert (400 touch, st4a = 6.5 V)

    @property
    def motor_power_params(self) -> tuple[float, float]:
        """EC-Motor-Zwei-Parameter-Modell: P = P_base + k × (RPM/RPM_ref)³.

        Berechnet P_base (fixer Overhead: Steuerelektronik + Mindesterregung)
        und k (aerodynamischer Anteil) per Least-Squares aus den konfigurierten
        Watt-Messwerten und den bekannten RPM-Verhältnissen.

        Für die 400-touch-Installation mit gemessenen Werten ergibt sich:
          P_base ≈ 8.93 W, k ≈ 71.71 W  (R² = 0.9989, max Residuum 1.5 W)

        Reines P ∝ n³ würde Stufe 1 um 72 % unterschätzen — nicht verwenden.
        Gibt (P_base, k_aero) zurück.
        """
        from .const import RPM_DEFAULTS
        rpm_ref = self.rpm_reference_stufe4

        # x_s = (RPM_s / RPM_ref)³  — RPM aus Analytics-Baseline oder Standardwerten
        x_vals: list[float] = []
        y_vals: list[float] = []
        for level in range(1, 5):
            rpm_level: float | None = None
            if self._analytics is not None:
                rpm_level = self._analytics.rpm_level_baseline(level)
            if rpm_level is None:
                rpm_level = RPM_DEFAULTS.get(level, rpm_ref * level / 4)
            x_vals.append((rpm_level / rpm_ref) ** 3)
            y_vals.append(self.watt_map.get(level, 0.0))

        # Einfache lineare Regression: y = P_base + k * x
        n = len(x_vals)
        xm = sum(x_vals) / n
        ym = sum(y_vals) / n
        num = sum((xi - xm) * (yi - ym) for xi, yi in zip(x_vals, y_vals))
        den = sum((xi - xm) ** 2 for xi in x_vals)
        if den < 1e-9:
            return 0.0, y_vals[-1]
        k = num / den
        p_base = ym - k * xm
        return max(0.0, p_base), max(0.0, k)

    @property
    def fan_law_consistency(self) -> dict[int, float] | None:
        """Residuen des EC-Motor-Zwei-Parameter-Modells pro Stufe in Prozent von P_Stufe4.

        Positiver Wert: gemessene Leistung höher als Modell vorhersagt.
        Negativer Wert: gemessene Leistung niedriger als Modell vorhersagt.

        Erwartungswert bei gesundem Motor mit guten Messwerten: < ±2 %.
        Werte > ±5 % (von P_Stufe4) deuten auf Messfehler oder Motoranomalie.
        Benötigt RPM-Daten (Analytics-Baseline oder aktueller Poll).

        Wichtig: Reines P ∝ n³ würde bei Stufe 1 eine Abweichung von 256 % zeigen
        (gemessene 11 W vs. 3 W fan-law). Das ist kein Fehler — EC-Motoren haben
        ~9 W Festanteil. Dieses Modell berücksichtigt diesen Anteil korrekt.
        """
        if self.data is None:
            return None

        # RPM-Werte für jede Stufe sammeln
        from .const import RPM_DEFAULTS
        rpm_ref = self.rpm_reference_stufe4
        rpm: dict[int, float] = {}
        for level in range(1, 5):
            baseline: float | None = None
            if self._analytics is not None:
                baseline = self._analytics.rpm_level_baseline(level)
            rpm[level] = baseline if baseline is not None else RPM_DEFAULTS.get(level, 0.0)

        if any(v == 0.0 for v in rpm.values()):
            return None

        p_base, k_aero = self.motor_power_params
        w4 = self.watt_map.get(4, 80.0)
        if w4 == 0:
            return None

        result: dict[int, float] = {}
        for level in range(1, 5):
            predicted = p_base + k_aero * (rpm[level] / rpm_ref) ** 3
            measured = self.watt_map.get(level, 0.0)
            result[level] = round((measured - predicted) / w4 * 100, 1)
        return result

    @property
    def spi_per_level(self) -> dict[int, float] | None:
        """Specific Power Input (W pro m³/h) pro Stufe.

        SPI[level] = watt_measured[level] / Q_estimated[level]

        Baseline beim Ersteinrichten des Geraets. Steigende SPI bei
        Nachfolgemessung = Motorverschleiss oder Filterverstopfung.
        Herstellerreferenz: 0.34 W/(m³/h) bei Bezugs-Volumenstrom 280 m³/h, 50 Pa.
        Installierte Werte typisch niedriger (geringerer Leitungsdruck).
        """
        if self.data is None:
            return None
        # Verwende Analytics-RPM-Baselines wenn verfuegbar
        q_ref, rpm_ref_val = 280.0, 2085.0  # 400-touch Standardwerte
        result: dict[int, float] = {}
        for level in range(1, 5):
            watt = self.watt_map.get(level)
            if watt is None:
                continue
            # RPM fuer Volumenstromschaetzung
            rpm_for_level: float | None = None
            if self._analytics is not None:
                rpm_for_level = self._analytics.rpm_level_baseline(level)
            if rpm_for_level is None and self.data.current_level == level:
                rpm_for_level = self.data.motor_abluft_rpm
            if rpm_for_level is None or rpm_for_level < 100:
                continue
            q_estimated = q_ref * rpm_for_level / rpm_ref_val
            result[level] = round(watt / q_estimated, 4)
        return result if result else None

    async def async_reset_analytics(self) -> None:
        """Setzt alle Analytics-Baselines zurueck (z.B. nach Filterwechsel)."""
        if self._analytics is not None:
            self._analytics.reset_baselines()
        if self._store is not None:
            await self._store.async_save({})
        _LOGGER.info("KWL Analytics-Baselines zurueckgesetzt")

    async def async_set_level(self, level: int) -> None:
        if level not in (1, 2, 3, 4):
            raise HomeAssistantError(f"Ungueltige Lüftungsstufe: {level}")
        url = f"http://{self.host}/stufe.cgi?stufe={level}"
        try:
            session = self._get_session()
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                resp.raise_for_status()
        except aiohttp.ClientError as err:
            raise HomeAssistantError(
                f"Fehler beim Setzen der Stufe {level}: {err}"
            ) from err
        await self.async_request_refresh()

    async def async_post_setup(self, payload: dict[str, str]) -> None:
        await self._post(f"http://{self.host}/setup.htm", payload, auth=None)

    async def async_post_install(self, payload: dict[str, str]) -> None:
        if self.capabilities and not self.capabilities.has_installer_access:
            raise HomeAssistantError("Installer-Bereich nicht verfuegbar auf diesem Geraet")
        await self._post(
            f"http://{self.host}/install/install.htm",
            payload,
            auth=self._install_auth,
        )

    async def _post(
        self,
        url: str,
        payload: dict[str, str],
        auth: aiohttp.BasicAuth | None,
    ) -> None:
        try:
            session = self._get_session()
            async with session.post(
                url,
                data=payload,
                auth=auth,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 401:
                    raise ConfigEntryAuthFailed(
                        "Authentifizierung fehlgeschlagen -- Zugangsdaten pruefen"
                    )
                resp.raise_for_status()
        except aiohttp.ClientError as err:
            raise HomeAssistantError(f"POST-Fehler an {url}: {err}") from err
        await self.async_request_refresh()


def _parse_xml(text: str) -> dict[str, str]:
    root = ElementTree.fromstring(text)
    return {child.tag: (child.text or "") for child in root}
