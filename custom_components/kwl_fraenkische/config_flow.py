"""Config Flow fuer die KWL Fraenkische Rohrwerke Integration."""
from __future__ import annotations

import logging
from xml.etree import ElementTree

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectOptionDict,
)

from .const import (
    CONF_MODEL, CONF_PROTOCOL, CONF_SCAN_INTERVAL,
    CONF_WATT_LEVEL_1, CONF_WATT_LEVEL_2, CONF_WATT_LEVEL_3, CONF_WATT_LEVEL_4,
    DEFAULT_MODEL, DEFAULT_MODBUS_PORT, DEFAULT_SCAN_INTERVAL, DEFAULT_WATT,
    DOMAIN, MAX_SCAN_INTERVAL, MIN_SCAN_INTERVAL,
    MODEL_DISPLAY, MODEL_PROFI_AIR_250, MODEL_PROFI_AIR_400,
    PROTOCOL_HTTP, PROTOCOL_MODBUS,
    UNIT_TYPE_TO_MODEL, WATT_DEFAULTS, WATT_MAX,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_HOST = "10.10.4.1"
DEFAULT_USERNAME = "install"


STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
    }
)

STEP_AUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME, default=DEFAULT_USERNAME): str,
        vol.Required(CONF_PASSWORD): vol.All(str, vol.Length(min=1)),
    }
)


class KWLConfigFlow(ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Config Flow: Protokoll-Erkennung → touch- oder flex-Pfad.

    Touch-Pfad (HTTP XML):
      1. IP → HTTP-Probe → installer_menu (Zugangsdaten eingeben / überspringen)
      2. auth (optional) → watt → Entry erstellen

    Flex-Pfad (Modbus TCP):
      1. IP → HTTP-Probe schlägt fehl → Modbus-Probe → confirm_flex
      2. Bestätigung → Entry erstellen (Watt-Werte in Options konfigurieren)
    """

    VERSION = 4

    def __init__(self) -> None:
        self._host: str = ""
        self._mac: str = ""
        self._username: str = ""
        self._password: str = ""
        # Flex-Pfad
        self._protocol: str = PROTOCOL_HTTP
        self._detected_model: str = DEFAULT_MODEL
        self._firmware_version: str = ""
        self._switch_position: str = "?"

    async def async_step_user(self, user_input: dict[str, str] | None = None) -> ConfigFlowResult:
        """Schritt 1: IP-Adresse → Protokoll-Erkennung."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()

            # ── HTTP-Probe (touch) ────────────────────────────────────────────
            result = await _fetch_device_info(host)
            if not isinstance(result, str):
                self._host = host
                self._mac = result["mac"]
                self._protocol = PROTOCOL_HTTP
                return await self.async_step_installer_menu()

            # ── Modbus-Probe (flex / flat) ────────────────────────────────────
            flex_result = await _probe_modbus(host)
            if flex_result is not None:
                if flex_result["model"] is None:
                    if flex_result["unit_type"] is None:
                        # Verbunden, aber keine Antwort auf Register-Abfrage
                        errors["base"] = "modbus_no_response"
                        return self.async_show_form(
                            step_id="user",
                            data_schema=STEP_USER_SCHEMA,
                            errors=errors,
                        )
                    # Verbunden + gelesen, aber Unit-Typ nicht bekannt
                    errors["base"] = "unknown_device_type"
                    return self.async_show_form(
                        step_id="user",
                        data_schema=STEP_USER_SCHEMA,
                        errors=errors,
                        description_placeholders={
                            "type_code": str(flex_result["unit_type"])
                        },
                    )
                self._host = host
                self._mac = flex_result["mac_id"]
                self._protocol = PROTOCOL_MODBUS
                self._detected_model = flex_result["model"]
                self._firmware_version = flex_result["firmware"]
                self._switch_position = flex_result["switch_position"]
                return await self.async_step_confirm_flex()

            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    async def async_step_installer_menu(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Menu: Installateur-Zugangsdaten eingeben oder überspringen.

        Mit Zugangsdaten: voller Schreibzugriff (Stufen, Betriebsmodus).
        Ohne Zugangsdaten: nur Lesen (status.xml ist öffentlich).
        """
        return self.async_show_menu(
            step_id="installer_menu",
            menu_options=["auth", "skip_installer"],
        )

    async def async_step_skip_installer(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Installateur-Zugangsdaten überspringen → nur Lesemodus."""
        self._username = ""
        self._password = ""
        return await self.async_step_watt()

    async def async_step_confirm_flex(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Flex/Flat-Gerät bestätigen und Entry erstellen."""
        if user_input is not None:
            await self.async_set_unique_id(self._mac)
            self._abort_if_unique_id_configured(updates={CONF_HOST: self._host})
            model_name = MODEL_DISPLAY.get(self._detected_model, self._detected_model)
            return self.async_create_entry(
                title=f"{model_name} ({self._host})",
                data={
                    CONF_HOST: self._host,
                    CONF_PROTOCOL: PROTOCOL_MODBUS,
                    "mac": self._mac,
                    "model": self._detected_model,
                    "firmware": self._firmware_version,
                },
            )

        return self.async_show_form(
            step_id="confirm_flex",
            data_schema=vol.Schema({}),  # Nur Bestätigung, keine Eingaben
            description_placeholders={
                "model": MODEL_DISPLAY.get(self._detected_model, self._detected_model),
                "firmware": self._firmware_version,
                "switch": self._switch_position,
                "host": self._host,
            },
        )

    async def async_step_auth(self, user_input: dict[str, str] | None = None) -> ConfigFlowResult:
        """Schritt 2: Installateur-Zugangsdaten."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]

            error = await _test_auth(self._host, username, password)
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(self._mac)
                self._abort_if_unique_id_configured(
                    updates={CONF_HOST: self._host}
                )
                self._username = username
                self._password = password
                return await self.async_step_watt()

        return self.async_show_form(
            step_id="auth",
            data_schema=STEP_AUTH_SCHEMA,
            errors=errors,
            description_placeholders={"host": self._host},
        )



    async def async_step_watt(
        self, user_input=None
    ) -> ConfigFlowResult:
        """Watt-Konfiguration (touch-Pfad). Flex überspringt diesen Schritt."""
        if user_input is not None:
            await self.async_set_unique_id(self._mac)
            self._abort_if_unique_id_configured(
                updates={CONF_HOST: self._host}
            )
            return self.async_create_entry(
                title=f"KWL ({self._host})",
                data={
                    CONF_HOST: self._host,
                    CONF_PROTOCOL: PROTOCOL_HTTP,
                    "mac": self._mac,
                    CONF_USERNAME: self._username,
                    CONF_PASSWORD: self._password,
                    CONF_WATT_LEVEL_1: user_input[CONF_WATT_LEVEL_1],
                    CONF_WATT_LEVEL_2: user_input[CONF_WATT_LEVEL_2],
                    CONF_WATT_LEVEL_3: user_input[CONF_WATT_LEVEL_3],
                    CONF_WATT_LEVEL_4: user_input[CONF_WATT_LEVEL_4],
                },
            )

        schema = vol.Schema({
            vol.Required(CONF_WATT_LEVEL_1, default=DEFAULT_WATT[1]): vol.All(
                vol.Coerce(float), vol.Range(min=1, max=500)
            ),
            vol.Required(CONF_WATT_LEVEL_2, default=DEFAULT_WATT[2]): vol.All(
                vol.Coerce(float), vol.Range(min=1, max=500)
            ),
            vol.Required(CONF_WATT_LEVEL_3, default=DEFAULT_WATT[3]): vol.All(
                vol.Coerce(float), vol.Range(min=1, max=500)
            ),
            vol.Required(CONF_WATT_LEVEL_4, default=DEFAULT_WATT[4]): vol.All(
                vol.Coerce(float), vol.Range(min=1, max=500)
            ),
        })

        return self.async_show_form(
            step_id="watt",
            data_schema=schema,
        )


    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Erstellt den Options Flow fuer diese Config Entry."""
        return KWLOptionsFlow(config_entry)

    async def async_step_reauth(
        self, entry_data: dict
    ) -> ConfigFlowResult:
        """Wird aufgerufen wenn ConfigEntryAuthFailed geworfen wird."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input=None
    ) -> ConfigFlowResult:
        """Neue Zugangsdaten abfragen."""
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])

        if user_input is not None:
            error = await _test_auth(
                entry.data[CONF_HOST],
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            if error:
                errors["base"] = error
            else:
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={
                        **entry.data,
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_AUTH_SCHEMA,
            errors=errors,
            description_placeholders={
                "host": entry.data.get(CONF_HOST, "")
            },
        )

    async def async_step_reconfigure(
        self, user_input=None
    ) -> ConfigFlowResult:
        """Erlaubt IP-Adresse und Zugangsdaten zu aendern ohne neu einzurichten."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()

            # Verbindung pruefen
            result = await _fetch_device_info(host)
            if isinstance(result, str):
                errors["base"] = result
            else:
                # Auth pruefen
                error = await _test_auth(
                    host,
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                )
                if error:
                    errors["base"] = error
                else:
                    # Bestehende entry.data beibehalten (Watt-Werte etc.)
                    # Nur geaenderte Felder ueberschreiben
                    self.hass.config_entries.async_update_entry(
                        entry,
                        data={
                            **entry.data,
                            CONF_HOST: host,
                            "mac": result["mac"],
                            CONF_USERNAME: user_input[CONF_USERNAME],
                            CONF_PASSWORD: user_input[CONF_PASSWORD],
                        },
                    )
                    await self.hass.config_entries.async_reload(entry.entry_id)
                    return self.async_abort(reason="reconfigure_successful")

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=entry.data.get(CONF_HOST, DEFAULT_HOST)): str,
                vol.Required(CONF_USERNAME, default=entry.data.get(CONF_USERNAME, DEFAULT_USERNAME)): str,
                vol.Required(CONF_PASSWORD): vol.All(str, vol.Length(min=1)),
            }
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
        )


class KWLOptionsFlow(OptionsFlow):
    """Options Flow: Konfigurierbare Parameter nach dem Setup.

    Touch (HTTP):
      - Gerätemodell (250 / 400 touch)
      - Poll-Intervall
      - Nennleistung Stufe 1–4 (Pflichtfeld, Standardwerte vorhanden)

    Flex / Flat (Modbus):
      - Poll-Intervall
      - Nennleistung Stufe 1–4 (Optional; None = Energieberechnung deaktiviert)
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Einziger Schritt — alle Optionen auf einer Seite."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        protocol = self._entry.data.get(CONF_PROTOCOL, PROTOCOL_HTTP)
        current = self._entry.options
        data = self._entry.data

        if protocol == PROTOCOL_MODBUS:
            return self.async_show_form(
                step_id="init",
                data_schema=self._flex_schema(current, data),
            )
        return self.async_show_form(
            step_id="init",
            data_schema=self._touch_schema(current, data),
        )

    def _touch_schema(self, current: dict, data: dict) -> vol.Schema:
        """Schema für touch-Einträge (Pflicht-Watt-Felder, Modell-Selektor)."""
        current_model = current.get(CONF_MODEL, DEFAULT_MODEL)
        model_watt_defaults = WATT_DEFAULTS.get(current_model, DEFAULT_WATT)

        return vol.Schema({
            vol.Required(
                CONF_MODEL,
                default=current_model,
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(
                            value=MODEL_PROFI_AIR_250,
                            label=MODEL_DISPLAY[MODEL_PROFI_AIR_250],
                        ),
                        SelectOptionDict(
                            value=MODEL_PROFI_AIR_400,
                            label=MODEL_DISPLAY[MODEL_PROFI_AIR_400],
                        ),
                    ],
                    mode="dropdown",
                )
            ),
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): vol.All(
                vol.Coerce(int),
                vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
            ),
            vol.Required(
                CONF_WATT_LEVEL_1,
                default=current.get(CONF_WATT_LEVEL_1,
                    data.get(CONF_WATT_LEVEL_1, model_watt_defaults[1])),
            ): vol.All(vol.Coerce(float), vol.Range(min=1, max=500)),
            vol.Required(
                CONF_WATT_LEVEL_2,
                default=current.get(CONF_WATT_LEVEL_2,
                    data.get(CONF_WATT_LEVEL_2, model_watt_defaults[2])),
            ): vol.All(vol.Coerce(float), vol.Range(min=1, max=500)),
            vol.Required(
                CONF_WATT_LEVEL_3,
                default=current.get(CONF_WATT_LEVEL_3,
                    data.get(CONF_WATT_LEVEL_3, model_watt_defaults[3])),
            ): vol.All(vol.Coerce(float), vol.Range(min=1, max=500)),
            vol.Required(
                CONF_WATT_LEVEL_4,
                default=current.get(CONF_WATT_LEVEL_4,
                    data.get(CONF_WATT_LEVEL_4, model_watt_defaults[4])),
            ): vol.All(vol.Coerce(float), vol.Range(min=1, max=500)),
        })

    def _flex_schema(self, current: dict, data: dict) -> vol.Schema:
        """Schema für flex/flat-Einträge (optionale Watt-Felder, kein Modell-Selektor).

        Watt-Werte sind Optional — None = Energieberechnung deaktiviert.
        WATT_MAX[model] wird als Obergrenze genutzt wenn bekannt.
        """
        model = data.get("model", "")
        max_watt = WATT_MAX.get(model, 500.0)

        def _opt_watt(level: int) -> vol.Optional:
            stored = current.get(f"watt_level_{level}", data.get(f"watt_level_{level}"))
            return vol.Optional(
                f"watt_level_{level}",
                default=stored,
            )

        watt_validator = vol.Any(
            None,
            vol.All(vol.Coerce(float), vol.Range(min=1, max=max_watt)),
        )

        return vol.Schema({
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): vol.All(
                vol.Coerce(int),
                vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
            ),
            _opt_watt(1): watt_validator,
            _opt_watt(2): watt_validator,
            _opt_watt(3): watt_validator,
            _opt_watt(4): watt_validator,
        })


async def _probe_modbus(
    host: str, port: int = DEFAULT_MODBUS_PORT
) -> dict | None:
    """Modbus-TCP Probe: verbindet, liest Gerätedaten, gibt dict oder None zurück.

    Drei Ergebnis-Klassen, jede mit eigener Bedeutung für die UI:
      None                                  → TCP-Verbindung fehlgeschlagen (Port nicht erreichbar)
      {"unit_type": None,  "model": None}   → TCP verbunden, aber Register-Read fehlgeschlagen
                                               (Modbus am Gerät deaktiviert, falsche Slave-ID, o.ä.)
      {"unit_type": X,     "model": None}   → verbunden + gelesen, aber Unit-Typ X unbekannt
      {"unit_type": X,     "model": "..."}  → vollständig erfolgreich
    """
    import logging as _log
    _log.getLogger("pymodbus").setLevel(_log.CRITICAL)

    try:
        from pymodbus.client import AsyncModbusTcpClient
        from pymodbus.client.mixin import ModbusClientMixin

        client = AsyncModbusTcpClient(host=host, port=port, timeout=3, retries=0)
        connected = await client.connect()
        if not connected:
            return None

        def _u32(regs: list) -> int:
            return ModbusClientMixin.convert_from_registers(
                regs[:2], ModbusClientMixin.DATATYPE.UINT32, "little"
            )

        try:
            # System-ID → Unit-Typ (Byte 0 des UINT32)
            r = await client.read_holding_registers(address=2, count=2, device_id=1)
            if r.isError():
                # TCP-Verbindung stand, aber das Gerät antwortet nicht auf die Abfrage.
                # Häufigste Ursachen: Modbus TCP am Gerät nicht aktiviert, falsche Slave-ID.
                _LOGGER.debug(
                    "Modbus-Probe: Verbindung zu %s erfolgreich, aber Register-Read fehlgeschlagen",
                    host,
                )
                return {"unit_type": None, "model": None}
            unit_type = _u32(r.registers) & 0xFF
            model = UNIT_TYPE_TO_MODEL.get(unit_type)
            if model is None:
                _LOGGER.debug("Modbus-Probe: unbekannter Unit-Typ %d auf %s", unit_type, host)
                return {"unit_type": unit_type, "model": None}

            # Firmware-Version
            fw_str = "?"
            r = await client.read_holding_registers(address=24, count=2, device_id=1)
            if not r.isError():
                fw_raw = _u32(r.registers)
                fw_str = f"{(fw_raw >> 8) & 0xFF}.{fw_raw & 0xFF}"

            # MAC-Adresse → Unique-ID
            mac_id = f"{host.replace('.', '')}_{unit_type}"  # Fallback
            r = await client.read_holding_registers(address=40, count=4, device_id=1)
            if not r.isError():
                mac_high = _u32(list(r.registers)[0:2])
                mac_low  = _u32(list(r.registers)[2:4])
                mac_id = f"{mac_high:08X}{mac_low:08X}"

            # A/B-Schalterstellung
            switch_pos = "?"
            r = await client.read_holding_registers(address=84, count=4, device_id=1)
            if not r.isError():
                hal_left = _u32(list(r.registers)[0:2])
                switch_pos = "B" if hal_left else "A"

            return {
                "unit_type": unit_type,
                "model": model,
                "mac_id": mac_id,
                "firmware": fw_str,
                "switch_position": switch_pos,
            }
        finally:
            client.close()

    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Modbus-Probe auf %s:%d fehlgeschlagen: %s", host, port, err)
        return None


async def _fetch_device_info(host: str) -> dict | str:
    """Prueft Erreichbarkeit und liest MAC aus status.xml."""
    url = f"http://{host}/status.xml"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    return "cannot_connect"
                text = await resp.text()
    except (aiohttp.ClientError, TimeoutError):
        # TimeoutError separat, da aiohttp.ClientTimeout bei Ablauf
        # asyncio.TimeoutError wirft — KEIN aiohttp.ClientError.
        # Ohne diesen Fang: unbehandelte Exception → HA zeigt "Unknown error
        # occurred" statt einer brauchbaren Meldung (betrifft v.a. nicht
        # erreichbare IPs, bei denen die Verbindung nicht aktiv abgelehnt wird).
        return "cannot_connect"

    try:
        root = ElementTree.fromstring(text)
        data = {child.tag: (child.text or "").strip() for child in root}
    except ElementTree.ParseError:
        return "invalid_response"

    if "config_mac" not in data:
        return "invalid_response"

    return {"mac": data["config_mac"]}


async def _test_auth(host: str, username: str, password: str) -> str | None:
    """Prueft ob die Zugangsdaten fuer /install/install.htm korrekt sind."""
    url = f"http://{host}/install/install.htm"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                auth=aiohttp.BasicAuth(username, password),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 401:
                    return "invalid_auth"
                if resp.status != 200:
                    return "cannot_connect"
    except (aiohttp.ClientError, TimeoutError):
        return "cannot_connect"
    return None
