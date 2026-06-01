"""KWL Fraenkische Rohrwerke - Home Assistant Integration."""
from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant

from .const import CONF_WATT_LEVEL_1, CONF_WATT_LEVEL_2, CONF_WATT_LEVEL_3, CONF_WATT_LEVEL_4, DEFAULT_WATT
from .coordinator import KWLCoordinator

PLATFORMS = [
    Platform.FAN,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.BUTTON,
]

# Typed ConfigEntry (HA 2024.4+)
type KWLConfigEntry = ConfigEntry[KWLCoordinator]


async def async_migrate_entry(hass: HomeAssistant, entry: KWLConfigEntry) -> bool:
    """Migriert bestehende Config Entries auf die aktuelle VERSION.

    v1 → v2: Watt-Werte wurden als Pflichtfelder hinzugefuegt.
              Fehlende Werte werden mit Standardwerten aufgefuellt.
    """
    _LOGGER.debug("Migriere KWL Config Entry von v%s", entry.version)

    if entry.version == 1:
        new_data = {**entry.data}
        # Watt-Werte ergaenzen falls sie fehlen (v1 hatte sie noch nicht)
        from .const import (
            CONF_WATT_LEVEL_1, CONF_WATT_LEVEL_2,
            CONF_WATT_LEVEL_3, CONF_WATT_LEVEL_4, DEFAULT_WATT,
        )
        for level, conf_key in [
            (1, CONF_WATT_LEVEL_1), (2, CONF_WATT_LEVEL_2),
            (3, CONF_WATT_LEVEL_3), (4, CONF_WATT_LEVEL_4),
        ]:
            new_data.setdefault(conf_key, DEFAULT_WATT[level])

        hass.config_entries.async_update_entry(
            entry, data=new_data, version=2
        )
        _LOGGER.info("KWL Config Entry auf v2 migriert")

    return True


async def _async_options_updated(
    hass: HomeAssistant, entry: KWLConfigEntry
) -> None:
    """Wird aufgerufen wenn Options geaendert werden -- Integration neu laden."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: KWLConfigEntry) -> bool:
    # Watt-Werte: options haben Vorrang vor data (nachtraegliche Aenderung via Options Flow)
    watt_map = {
        1: entry.options.get(CONF_WATT_LEVEL_1,
               entry.data.get(CONF_WATT_LEVEL_1, DEFAULT_WATT[1])),
        2: entry.options.get(CONF_WATT_LEVEL_2,
               entry.data.get(CONF_WATT_LEVEL_2, DEFAULT_WATT[2])),
        3: entry.options.get(CONF_WATT_LEVEL_3,
               entry.data.get(CONF_WATT_LEVEL_3, DEFAULT_WATT[3])),
        4: entry.options.get(CONF_WATT_LEVEL_4,
               entry.data.get(CONF_WATT_LEVEL_4, DEFAULT_WATT[4])),
    }
    coordinator = KWLCoordinator(
        hass,
        entry=entry,
        host=entry.data[CONF_HOST],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        watt_map=watt_map,
    )
    await coordinator.async_config_entry_first_refresh()

    # runtime_data ZUERST setzen -- async_setup() und Platforms koennen darauf zugreifen
    entry.runtime_data = coordinator

    # Zeitsynchronisation starten
    await coordinator.async_setup()

    # Bei Options-Aenderungen Integration neu laden (Poll-Intervall, Watt-Werte)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KWLConfigEntry) -> bool:
    unload_ok: bool = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: KWLCoordinator = entry.runtime_data
        coordinator.async_teardown()
    return bool(unload_ok)
