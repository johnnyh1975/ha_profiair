"""DataUpdateCoordinator fuer die Fraenkische Rohrwerke KWL-Integration."""
from __future__ import annotations

import logging
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
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=30)
TIME_SYNC_INTERVAL = timedelta(hours=24)


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


def _build_time_payload(now) -> dict[str, str]:
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


def _build_dst_payload(now) -> dict[str, str]:
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
    def control_mode(self) -> str:
        return self._raw.get("control0", "").strip()

    @property
    def bypass_status(self) -> str:
        return self._raw.get("bypass", "").strip()

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

        super().__init__(
            hass,
            _LOGGER,
            name="KWL Fraenkische Rohrwerke",
            update_interval=SCAN_INTERVAL,
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

        Startet die automatische Zeitsynchronisation:
        - Sofortige Synchronisation beim Start
        - Danach alle 24 Stunden
        - Sommer-/Winterzeit wird dabei automatisch mitgesetzt
        """
        await self._async_sync_time()

        self._unsub_time_sync = async_track_time_interval(
            self.hass,
            self._async_sync_time_callback,
            TIME_SYNC_INTERVAL,
        )
        _LOGGER.debug("KWL Zeitsynchronisation eingerichtet (alle 24h)")

    async def _async_sync_time_callback(self, _now=None) -> None:
        """Callback fuer den 24h-Timer."""
        await self._async_sync_time()

    async def _async_sync_time(self) -> None:
        """Sendet die aktuelle HA-Systemzeit und DST-Status an die KWL.

        Verwendet die HA-Zeitzone (dt_util.now()) damit Sommer-/Winterzeit
        korrekt aus der konfigurierten HA-Zeitzone abgeleitet wird.
        """
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

    def async_teardown(self) -> None:
        """Raeumt den Zeitsync-Listener auf beim Entladen der Integration."""
        if self._unsub_time_sync is not None:
            self._unsub_time_sync()
            self._unsub_time_sync = None

    async def async_close_session(self) -> None:
        """HA-Session wird von HA verwaltet -- nichts zu tun."""
        pass

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

        return data

    def _get_session(self) -> aiohttp.ClientSession:
        """Gibt die HA-verwaltete aiohttp Session zurueck."""
        return self._session

    async def async_set_level(self, level: int) -> None:
        if level not in (1, 2, 3, 4):
            raise HomeAssistantError(f"Ungueltige Lueeftungsstufe: {level}")
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
