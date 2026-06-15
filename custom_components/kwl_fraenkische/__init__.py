"""KWL Fraenkische Rohrwerke - Home Assistant Integration."""
from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import CONF_WATT_LEVEL_1, CONF_WATT_LEVEL_2, CONF_WATT_LEVEL_3, CONF_WATT_LEVEL_4, DEFAULT_WATT, CONF_PROTOCOL, PROTOCOL_HTTP, PROTOCOL_MODBUS
from .coordinator import KWLCoordinator
from .flex_coordinator import KWLFlexCoordinator

PLATFORMS = [
    Platform.FAN,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.BUTTON,
]

# Union-Typ für beide Coordinator-Familien
AnyKWLCoordinator = KWLCoordinator | KWLFlexCoordinator

# Typed ConfigEntry (HA 2024.4+)
type KWLConfigEntry = ConfigEntry[AnyKWLCoordinator]


async def async_migrate_entry(hass: HomeAssistant, entry: KWLConfigEntry) -> bool:
    """Migriert bestehende Config Entries auf die aktuelle VERSION.

    v1 → v2: Watt-Werte wurden als Pflichtfelder hinzugefuegt.
    v2 → v3: Entity-IDs vereinheitlicht auf kwl_{key} Schema.
              Bereinigt inkonsistente Prefixe aus verschiedenen Versionen
              (kwl_fraenkische_rohrwerke_*, profi_air_400_*, dachboden_*).
    """
    _LOGGER.debug("Migriere KWL Config Entry von v%s", entry.version)

    if entry.version == 1:
        new_data = {**entry.data}
        from .const import (
            CONF_WATT_LEVEL_1, CONF_WATT_LEVEL_2,
            CONF_WATT_LEVEL_3, CONF_WATT_LEVEL_4, DEFAULT_WATT,
        )
        for level, conf_key in [
            (1, CONF_WATT_LEVEL_1), (2, CONF_WATT_LEVEL_2),
            (3, CONF_WATT_LEVEL_3), (4, CONF_WATT_LEVEL_4),
        ]:
            new_data.setdefault(conf_key, DEFAULT_WATT[level])

        hass.config_entries.async_update_entry(entry, data=new_data, version=2)
        _LOGGER.info("KWL Config Entry auf v2 migriert")

    if entry.version == 2:
        entity_registry = er.async_get(hass)
        mac = entry.data.get("mac", "")
        from .const import CONF_MODEL, DEFAULT_MODEL
        model = entry.options.get(CONF_MODEL, DEFAULT_MODEL)  # e.g. "profi_air_400"
        migrated = 0
        skipped = 0

        for entity_entry in er.async_entries_for_config_entry(
            entity_registry, entry.entry_id
        ):
            uid = entity_entry.unique_id

            # Schluessel aus unique_id extrahieren: Format ist "{mac}_{key}"
            if mac and uid.startswith(mac + "_"):
                key = uid[len(mac) + 1:]
            elif mac and uid == mac:
                key = model  # Fan-Entity: unique_id ist nur MAC
            else:
                _LOGGER.warning("Unbekanntes unique_id Format: %s -- übersprungen", uid)
                skipped += 1
                continue

            # Fan: entity_id = "fan.profi_air_400", alle anderen: "{domain}.{model}_{key}"
            if entity_entry.domain == "fan" and key == model:
                new_entity_id = f"fan.{model}"
            else:
                new_entity_id = f"{entity_entry.domain}.{model}_{key}"

            if entity_entry.entity_id == new_entity_id:
                continue  # Bereits korrekt

            conflict = entity_registry.async_get(new_entity_id)
            if conflict is not None and conflict.unique_id != uid:
                _LOGGER.warning(
                    "Kann %s nicht zu %s migrieren: Ziel-ID belegt von %s",
                    entity_entry.entity_id, new_entity_id, conflict.unique_id,
                )
                skipped += 1
                continue

            entity_registry.async_update_entity(
                entity_entry.entity_id, new_entity_id=new_entity_id
            )
            _LOGGER.debug("Entity migriert: %s → %s", entity_entry.entity_id, new_entity_id)
            migrated += 1

        hass.config_entries.async_update_entry(entry, version=3)
        _LOGGER.info(
            "KWL auf v3 migriert: %d Entity-IDs vereinheitlicht auf %s_*, %d uebersprungen",
            migrated, model, skipped,
        )

    if entry.version == 3:
        # v3 → v4: Zwei Korrekturen für v2.0.0-Kompatibilität
        #
        # 1) CONF_PROTOCOL ergänzen – bestehende touch-Einträge kennen dieses Feld noch nicht.
        #    Ohne es würde async_setup_entry einen KeyError werfen sobald der Flex-Zweig
        #    abgefragt wird.
        #
        # 2) Fan-Entity-ID bereinigen – die v2→v3-Migration hat für Einträge mit
        #    unique_id="{mac}_fan" fälschlicherweise "fan.{model}_fan" statt "fan.{model}"
        #    geschrieben. Das wird hier korrigiert.

        # Schritt 1: Protokoll-Konstante ergänzen
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_PROTOCOL: PROTOCOL_HTTP},
            version=4,
        )
        _LOGGER.info(
            "KWL Entry %s auf v4 migriert: CONF_PROTOCOL=http gesetzt",
            entry.entry_id,
        )

        # Schritt 2: Fan-Entity-ID normalisieren (entfernt fälschlichen _fan-Suffix)
        entity_registry = er.async_get(hass)
        for entity_entry in er.async_entries_for_config_entry(
            entity_registry, entry.entry_id
        ):
            if entity_entry.domain != "fan":
                continue
            old_id = entity_entry.entity_id
            # Entfernt "_fan"-Suffix falls vorhanden (z.B. "fan.profi_air_400_fan" → "fan.profi_air_400")
            if not old_id.endswith("_fan"):
                continue
            new_id = old_id[:-4]  # "_fan" = 4 Zeichen
            if entity_registry.async_get(new_id) is not None:
                _LOGGER.warning(
                    "Fan-Entity-Migration: Ziel-ID %s bereits belegt – %s bleibt unverändert",
                    new_id, old_id,
                )
                continue
            entity_registry.async_update_entity(old_id, new_entity_id=new_id)
            _LOGGER.info("Fan-Entity migriert: %s → %s", old_id, new_id)

    return True


async def _async_options_updated(
    hass: HomeAssistant, entry: KWLConfigEntry
) -> None:
    """Wird aufgerufen wenn Options geaendert werden -- Integration neu laden."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: KWLConfigEntry) -> bool:
    protocol = entry.data.get(CONF_PROTOCOL, PROTOCOL_HTTP)

    if protocol == PROTOCOL_MODBUS:
        # ── Flex / Flat Pfad (Modbus TCP) ────────────────────────────────────
        coordinator = KWLFlexCoordinator(hass, entry=entry)
        await coordinator.async_config_entry_first_refresh()
        entry.runtime_data = coordinator
        await coordinator.async_setup()

    else:
        # ── Touch Pfad (HTTP XML) ─────────────────────────────────────────────
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
            username=entry.data.get(CONF_USERNAME, ""),
            password=entry.data.get(CONF_PASSWORD, ""),
            watt_map=watt_map,
        )
        await coordinator.async_config_entry_first_refresh()
        entry.runtime_data = coordinator
        await coordinator.async_setup()

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KWLConfigEntry) -> bool:
    unload_ok: bool = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: AnyKWLCoordinator = entry.runtime_data
        coordinator.async_teardown()
    return bool(unload_ok)
