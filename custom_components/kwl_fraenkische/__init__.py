"""KWL Fraenkische Rohrwerke - Home Assistant Integration."""
from __future__ import annotations

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


async def async_setup_entry(hass: HomeAssistant, entry: KWLConfigEntry) -> bool:
    # Watt-Werte aus Config Entry -- Fallback auf Standardwerte fuer bestehende Eintraege
    watt_map = {
        1: entry.data.get(CONF_WATT_LEVEL_1, DEFAULT_WATT[1]),
        2: entry.data.get(CONF_WATT_LEVEL_2, DEFAULT_WATT[2]),
        3: entry.data.get(CONF_WATT_LEVEL_3, DEFAULT_WATT[3]),
        4: entry.data.get(CONF_WATT_LEVEL_4, DEFAULT_WATT[4]),
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
    await coordinator.async_setup()

    # Modernes runtime_data Pattern (HA 2024.4+)
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KWLConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: KWLCoordinator = entry.runtime_data
        coordinator.async_teardown()
        await coordinator.async_close_session()
    return unload_ok
