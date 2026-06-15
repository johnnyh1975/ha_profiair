"""Repair Issues fuer die KWL Fraenkische Rohrwerke Integration."""
from __future__ import annotations

import logging
from typing import Any, cast

import voluptuous as vol

from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from . import KWLConfigEntry
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Erstellt den passenden Fix-Flow fuer ein Repair Issue."""
    if issue_id == "filter_needs_replacement":
        return FilterRepairFlow()
    if issue_id in ("annual_maintenance_due", "annual_maintenance"):
        return AnnualMaintenanceRepairFlow()
    return ConfirmRepairFlow()


def _get_coordinator(hass: HomeAssistant, data: dict | None) -> Any | None:
    """Hilfsfunktion: Coordinator aus entry_id holen."""
    entry_id = (data or {}).get("entry_id")
    if not entry_id:
        return None
    entry = hass.config_entries.async_get_entry(entry_id)
    return entry.runtime_data if entry else None


class FilterRepairFlow(RepairsFlow):
    """Repair Flow fuer den Filterwechsel-Alarm.

    Fuehrt den Nutzer durch:
    1. Filter tatsaechlich wechseln
    2. Alarm am Geraet quittieren via filter.cgi
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if user_input is not None:
            coordinator = _get_coordinator(
                self.hass,
                self.data if hasattr(self, "data") else None,
            )
            if coordinator:
                try:
                    url = f"http://{coordinator.host}/filter.cgi?filter=1"
                    session = coordinator._get_session()
                    async with session.get(url) as resp:
                        resp.raise_for_status()
                    await coordinator.async_request_refresh()
                    _LOGGER.info("KWL Filterwechsel-Alarm quittiert")
                except Exception as err:
                    _LOGGER.warning("Fehler beim Quittieren des Filteralarms: %s", err)

            ir.async_delete_issue(self.hass, DOMAIN, "filter_needs_replacement")
            return self.async_create_entry(data={})  # type: ignore[no-any-return]

        return cast(dict[str, Any], self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
        ))


class AnnualMaintenanceRepairFlow(RepairsFlow):
    """Repair Flow fuer die Jahreswartungs-Erinnerung.

    Setzt _maintenance_acknowledged=True auf dem Coordinator damit
    das Issue nicht beim naechsten Poll sofort wieder erscheint.
    Das Flag bleibt gesetzt bis die Integration neu gestartet wird
    (nach einem Jahr laeuft der Zaehler ohnehin weiter).
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if user_input is not None:
            coordinator = _get_coordinator(
                self.hass,
                self.data if hasattr(self, "data") else None,
            )
            if coordinator:
                from .coordinator import ANNUAL_MAINTENANCE_HOURS
                from .const import CONF_PROTOCOL, PROTOCOL_MODBUS

                entry = coordinator.config_entry
                protocol = entry.data.get(CONF_PROTOCOL, "http")

                if protocol == PROTOCOL_MODBUS:
                    # Flex: async_reset_analytics() kümmert sich um Threshold
                    await coordinator.async_reset_analytics()
                else:
                    # Touch: Stunden der 4 Stufen summieren
                    data = coordinator.data
                    current = sum(filter(None, [
                        data.hours_level_1 if data else None,
                        data.hours_level_2 if data else None,
                        data.hours_level_3 if data else None,
                        data.hours_level_4 if data else None,
                    ]))
                    new_threshold = current + ANNUAL_MAINTENANCE_HOURS
                    coordinator._maintenance_next_threshold = new_threshold
                    self.hass.config_entries.async_update_entry(
                        entry,
                        data={
                            **entry.data,
                            "maintenance_next_threshold": new_threshold,
                        },
                    )
                    _LOGGER.info(
                        "KWL Jahreswartung quittiert -- naechste Warnung bei %.0f Betriebsstunden",
                        new_threshold,
                    )

            ir.async_delete_issue(self.hass, DOMAIN, "annual_maintenance_due")
            ir.async_delete_issue(self.hass, DOMAIN, "annual_maintenance")
            return self.async_create_entry(data={})  # type: ignore[no-any-return]

        return cast(dict[str, Any], self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
        ))
