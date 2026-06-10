"""Config Flow fuer die KWL Fraenkische Rohrwerke Integration."""
from __future__ import annotations

from xml.etree import ElementTree

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME

from .const import (
    CONF_MODEL, CONF_SCAN_INTERVAL, CONF_WATT_LEVEL_1, CONF_WATT_LEVEL_2,
    CONF_WATT_LEVEL_3, CONF_WATT_LEVEL_4,
    DEFAULT_MODEL, DEFAULT_SCAN_INTERVAL, DEFAULT_WATT,
    DOMAIN, MAX_SCAN_INTERVAL, MIN_SCAN_INTERVAL,
    MODEL_PROFI_AIR_250, MODEL_PROFI_AIR_400, WATT_DEFAULTS,
)

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
    """Zweistufiger Config Flow:
    Schritt 1 -- IP-Adresse eingeben und Verbindung pruefen
    Schritt 2 -- Installateur-Zugangsdaten eingeben und pruefen
    """

    VERSION = 2

    def __init__(self) -> None:
        self._host: str = ""
        self._mac: str = ""
        self._username: str = ""
        self._password: str = ""

    async def async_step_user(self, user_input: dict[str, str] | None = None) -> ConfigFlowResult:
        """Schritt 1: IP-Adresse."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            result = await _fetch_device_info(host)

            if isinstance(result, str):
                errors["base"] = result
            else:
                self._host = host
                self._mac = result["mac"]
                # Weiter zu Schritt 2: Auth
                return await self.async_step_auth()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
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
        """Schritt 3: Nennleistung pro Stufe konfigurieren."""
        if user_input is not None:
            await self.async_set_unique_id(self._mac)
            self._abort_if_unique_id_configured(
                updates={CONF_HOST: self._host}
            )
            return self.async_create_entry(
                title=f"KWL ({self._host})",
                data={
                    CONF_HOST: self._host,
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
    """Options Flow fuer konfigurierbare Parameter nach dem Setup.

    Erlaubt Aenderung von:
    - Geraetemodell (profi-air 250 touch / profi-air 400 touch)
    - Poll-Intervall (30-300 Sekunden)
    - Nennleistung pro Stufe (fuer korrekte Energieberechnung)
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Einziger Schritt -- alle Optionen auf einer Seite."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self._entry.options
        data = self._entry.data

        # Aktuelles Modell -- bestimmt die Watt-Standardwerte
        current_model = current.get(CONF_MODEL, DEFAULT_MODEL)
        model_watt_defaults = WATT_DEFAULTS.get(current_model, DEFAULT_WATT)

        schema = vol.Schema({
            vol.Required(
                CONF_MODEL,
                default=current_model,
            ): vol.In([MODEL_PROFI_AIR_250, MODEL_PROFI_AIR_400]),
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

        return self.async_show_form(step_id="init", data_schema=schema)


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
    except aiohttp.ClientError:
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
    except aiohttp.ClientError:
        return "cannot_connect"
    return None
