"""Coordinator für profi-air 140/200 lite (REST/JSON, EXPERIMENTELL).

Siehe docs/lite-rest.md. Fragt ``GET status`` lokal ab und bietet die beiden
Schreibaktionen, die die App am Gerät selbst ausführt: Ein/Aus und die
Lüftungsfunktion (Auto, Nacht, Min, Max).
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_SCAN_INTERVAL,
    DOMAIN,
    LITE_DEFAULT_SCAN_INTERVAL,
    LITE_MIN_SCAN_INTERVAL,
    MODEL_DISPLAY_LITE,
    MODEL_PROFI_AIR_LITE,
)
from .lite_client import (
    KWLLiteClient,
    KWLLiteData,
    LiteConnectionError,
    LiteError,
    LiteResponseError,
    LiteUnsupportedDevice,
)

_LOGGER = logging.getLogger(__name__)


class KWLLiteCoordinator(DataUpdateCoordinator[KWLLiteData]):
    """Pollt den lokalen Status eines 140/200 lite."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._host: str = entry.data[CONF_HOST]
        scan_seconds = max(
            LITE_MIN_SCAN_INTERVAL,
            int(entry.options.get(CONF_SCAN_INTERVAL, LITE_DEFAULT_SCAN_INTERVAL)),
        )
        super().__init__(
            hass,
            _LOGGER,
            name="KWL Fränkische lite",
            update_interval=timedelta(seconds=scan_seconds),
            config_entry=entry,
        )
        self.client = KWLLiteClient(async_get_clientsession(hass), self._host)
        self._uid: str = entry.data.get("mac", entry.entry_id)
        self.device_info: DeviceInfo = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("name") or "profi-air lite",
            manufacturer="Fränkische Rohrwerke",
            model=MODEL_DISPLAY_LITE,
            sw_version=entry.data.get("firmware") or None,
            serial_number=entry.data.get("serial") or None,
            configuration_url=f"http://{self._host}/",
        )

    @property
    def model_slug(self) -> str:
        return MODEL_PROFI_AIR_LITE

    @property
    def unique_prefix(self) -> str:
        return self._uid

    async def async_setup(self) -> None:
        """Hook der anderen Coordinator-Familien; hier nichts einzurichten."""

    def async_teardown(self) -> None:
        """Hook der anderen Coordinator-Familien; hier nichts aufzuräumen."""

    async def _async_update_data(self) -> KWLLiteData:
        try:
            data = await self.client.get_status()
        except LiteConnectionError as err:
            raise UpdateFailed(f"{self._host} nicht erreichbar: {err}") from err
        except LiteUnsupportedDevice as err:
            raise UpdateFailed(str(err)) from err
        except LiteResponseError as err:
            raise UpdateFailed(f"Unerwartete Antwort von {self._host}: {err}") from err

        # Firmware kann sich nach einem Update ändern.
        if data.firmware and data.firmware != self.device_info.get("sw_version"):
            self.device_info["sw_version"] = data.firmware
        return data

    # ── Schreibaktionen (jede endet mit einem Refresh) ───────────────────────

    async def _write(self, action: Any, *args: Any) -> None:
        try:
            await action(*args)
        except LiteError as err:
            # Als HA-Fehler melden, damit der Aufrufer (UI/Automation) ihn sieht.
            raise HomeAssistantError(f"{self._host}: {err}") from err
        await self.async_request_refresh()

    async def async_set_power(self, on: bool) -> None:
        await self._write(self.client.async_set_power, on)

    async def async_set_function(self, function: str) -> None:
        await self._write(self.client.async_set_function, function)
