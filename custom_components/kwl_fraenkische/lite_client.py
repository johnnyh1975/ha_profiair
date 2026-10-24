"""REST/JSON-Client für profi-air 140/200 lite (Innova-WLAN-Modul).

EXPERIMENTELL -- abgeleitet aus der Analyse der Hersteller-App „profi-air smart
control“ 1.2.6, noch nicht an einem echten Gerät getestet. Siehe
docs/lite-rest.md.

Das WLAN-Modul (ESP8266, Innova-Plattform, ``deviceType "002"``) bietet eine
unverschlüsselte REST/JSON-API ohne lokale Authentifizierung unter
``http://<ip>/api/v/1/``. Dieses Modul spricht sie ausschließlich lokal an
(nicht über die Innova-Cloud) und kennt nur Befehle, die die App selbst nutzt.

Bewusst NICHT enthalten: ``rs485/write`` und ``setup`` / ``network/set`` -- sie
schreiben Geräteregister bzw. Netzwerkkonfiguration und könnten das Gerät
unbrauchbar machen.

Dieses Modul importiert nichts aus Home Assistant und ist daher eigenständig
testbar.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Final

import aiohttp

_LOGGER = logging.getLogger(__name__)

API_PREFIX: Final[str] = "/api/v/1/"

# Die App akzeptiert nur Geräte ohne deviceType-Feld oder mit "002".
SUPPORTED_DEVICE_TYPES: Final[frozenset[str]] = frozenset({"", "002"})

# RESULT.fn ↔ Funktionsname (settings.js: FUNCTION_AUTO=1 … FUNCTION_MAX=4)
FUNCTION_CODE_TO_NAME: Final[dict[int, str]] = {
    1: "auto",
    2: "night",
    3: "min",
    4: "max",
}
FUNCTION_NAMES: Final[tuple[str, ...]] = tuple(FUNCTION_CODE_TO_NAME.values())

# RESULT.wm ↔ Betriebsart (settings.js: MODE_HEATING=3, MODE_COOLING=5)
SEASON_CODE_TO_NAME: Final[dict[int, str]] = {3: "heating", 5: "cooling"}

# Alarm-String der App für "Kontaktanwesenheit" (z. B. Fensterkontakt): das
# Gerät ist dann gesperrt, die App zeigt es als "in Standby".
ALARM_CONTACT_PRESENCE: Final[str] = "CP"

DEFAULT_TIMEOUT: Final[float] = 10.0


class LiteError(Exception):
    """Basisklasse für Fehler dieses Clients."""


class LiteConnectionError(LiteError):
    """Gerät nicht erreichbar (Netzwerk, Timeout, HTTP-Status)."""


class LiteResponseError(LiteError):
    """Gerät antwortet, aber nicht wie erwartet oder mit ``success: false``."""

    def __init__(self, message: str, error_code: str | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code


class LiteUnsupportedDevice(LiteError):
    """Antwort stammt von einer nicht unterstützten Gerätefamilie."""


@dataclass(frozen=True)
class KWLLiteData:
    """Dekodierter Status eines 140/200 lite.

    Skalierungen wie in der App (homepageController.js): Temperaturen und
    Sollwert in °C × 10, Feuchte in % × 10, Luftqualität als Rohwert (Stufe =
    round(Rohwert / 100), mindestens 1).
    """

    powered: bool
    function: str | None          # auto | night | min | max | None
    season: str | None            # heating | cooling | None
    room_temp: float | None       # °C
    water_temp: float | None      # °C (None wenn kein Register verbaut)
    setpoint: float | None        # °C
    setpoint_min: float | None
    setpoint_max: float | None
    humidity: int | None          # %
    air_quality_raw: int | None
    air_quality_level: int | None  # 1–5 (App-Anzeige)
    calendar_active: bool
    key_lock: bool
    alarms: tuple[str, ...]
    heating_disabled: bool
    standalone: bool              # True: Gerät läuft im eigenen WLAN (kein Heimnetz)
    uid: str | None
    serial: str | None
    name: str | None
    firmware: str | None
    ip: str | None
    device_type: str
    result: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def contact_presence(self) -> bool:
        """Fensterkontakt o. ä. hat das Gerät gesperrt (Alarm ``CP``)."""
        return ALARM_CONTACT_PRESENCE in self.alarms

    @property
    def has_alarm(self) -> bool:
        """Irgendein Alarm außer der reinen Kontaktanwesenheit."""
        return any(a != ALARM_CONTACT_PRESENCE for a in self.alarms)

    @property
    def running(self) -> bool:
        """Gerät ist eingeschaltet UND nicht durch Kontaktanwesenheit gesperrt
        (so wertet es die App aus: ``active``)."""
        return self.powered and not self.contact_presence


def _num(value: Any) -> float | None:
    """Wandelt Zahl oder Zahlenstring in float; sonst None."""
    if isinstance(value, bool):
        return None
    num: float | None = None
    if isinstance(value, (int, float)):
        num = float(value)
    elif isinstance(value, str):
        try:
            num = float(value.strip())
        except ValueError:
            return None
    return num if num is not None and math.isfinite(num) else None


def _tenths(value: Any) -> float | None:
    """°C × 10 → °C. Negative Werte bedeuten 'nicht vorhanden'."""
    num = _num(value)
    if num is None or num < 0:
        return None
    return round(num / 10.0, 1)


def _str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_status(payload: Any) -> KWLLiteData:
    """Wandelt die Antwort von ``GET status`` in :class:`KWLLiteData`.

    Tolerant gegenüber fehlenden Feldern (Firmware-Varianten), streng bei der
    Grundform und der Gerätefamilie.

    Raises:
        LiteResponseError: kein JSON-Objekt, ``success`` ≠ true, kein ``RESULT``.
        LiteUnsupportedDevice: ``deviceType`` nicht in SUPPORTED_DEVICE_TYPES.
    """
    if not isinstance(payload, dict):
        raise LiteResponseError("Antwort ist kein JSON-Objekt")
    if payload.get("success") is not True:
        raise LiteResponseError(
            f"Gerät meldet Fehler: {payload.get('error', 'unbekannt')}",
            error_code=_str(payload.get("error")),
        )

    device_type = _str(payload.get("deviceType")) or ""
    if device_type not in SUPPORTED_DEVICE_TYPES:
        raise LiteUnsupportedDevice(f"deviceType {device_type!r} wird nicht unterstützt")

    result = payload.get("RESULT")
    if not isinstance(result, dict):
        raise LiteResponseError("Antwort enthält kein RESULT-Objekt")

    fn_raw = _num(result.get("fn"))
    wm_raw = _num(result.get("wm"))

    humidity_raw = _num(result.get("humidity"))
    humidity = int(humidity_raw / 10) if humidity_raw is not None and humidity_raw > 0 else None

    aq_raw_f = _num(result.get("airQuality"))
    aq_raw = int(aq_raw_f) if aq_raw_f is not None and aq_raw_f > 0 else None
    aq_level = max(1, round(aq_raw / 100)) if aq_raw is not None else None

    alarms_raw = result.get("a")
    alarms = (
        tuple(str(a) for a in alarms_raw if a not in (None, ""))
        if isinstance(alarms_raw, list) else ()
    )

    setup = payload.get("setup") if isinstance(payload.get("setup"), dict) else {}
    sw = payload.get("sw") if isinstance(payload.get("sw"), dict) else {}
    net = payload.get("net") if isinstance(payload.get("net"), dict) else {}

    return KWLLiteData(
        powered=(_num(result.get("ps")) or 0) != 0,
        function=FUNCTION_CODE_TO_NAME.get(int(fn_raw)) if fn_raw is not None else None,
        season=SEASON_CODE_TO_NAME.get(int(wm_raw)) if wm_raw is not None else None,
        room_temp=_tenths(result.get("ta")),
        water_temp=_tenths(result.get("tw")),
        setpoint=_tenths(result.get("sp")),
        setpoint_min=_tenths(result.get("spl")),
        setpoint_max=_tenths(result.get("sph")),
        humidity=humidity,
        air_quality_raw=aq_raw,
        air_quality_level=aq_level,
        calendar_active=bool(_num(result.get("cm"))),
        key_lock=bool(_num(result.get("kl"))),
        alarms=alarms,
        heating_disabled=bool(_num(result.get("heatingDisabled"))),
        standalone=_num(result.get("ns")) == 1,
        uid=_str(payload.get("UID")),
        serial=_str(setup.get("serial")),
        name=_str(setup.get("name")),
        firmware=_str(sw.get("V")),
        ip=_str(net.get("ip")),
        device_type=device_type,
        result=dict(result),
    )


class KWLLiteClient:
    """Lokaler Client für die REST-API des lite-WLAN-Moduls.

    Die Session gehört dem Aufrufer (in Home Assistant: die geteilte
    ``async_get_clientsession``). Schreibende Aufrufe senden -- wie die App --
    einen JSON-String als Body mit ``Content-Type: application/x-www-form-urlencoded``.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._session = session
        self._host = host
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    @property
    def host(self) -> str:
        return self._host

    def _url(self, path: str) -> str:
        return f"http://{self._host}{API_PREFIX}{path}"

    async def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> Any:
        kwargs: dict[str, Any] = {"timeout": self._timeout}
        if body is not None:
            kwargs["data"] = json.dumps(body)
            kwargs["headers"] = {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            async with self._session.request(method, self._url(path), **kwargs) as resp:
                if resp.status != 200:
                    raise LiteConnectionError(f"HTTP {resp.status} für {path}")
                try:
                    return await resp.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError) as err:
                    raise LiteResponseError(f"Ungültiges JSON von {path}") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise LiteConnectionError(f"{self._host}: {err}") from err

    @staticmethod
    def _check_success(payload: Any, path: str) -> None:
        if not isinstance(payload, dict) or payload.get("success") is not True:
            code = payload.get("error") if isinstance(payload, dict) else None
            raise LiteResponseError(
                f"{path} abgelehnt (error={code!r})", error_code=_str(code)
            )

    async def get_status(self) -> KWLLiteData:
        """Liest und dekodiert ``GET status``."""
        return parse_status(await self._request("GET", "status"))

    async def async_set_power(self, on: bool) -> None:
        path = "power/on" if on else "power/off"
        self._check_success(await self._request("POST", path), path)

    async def async_set_function(self, function: str) -> None:
        """Setzt die Lüftungsfunktion (auto | night | min | max)."""
        if function not in FUNCTION_NAMES:
            raise ValueError(f"Unbekannte Funktion: {function!r}")
        path = f"set/function/{function}"
        self._check_success(await self._request("POST", path, {"value": 1}), path)
