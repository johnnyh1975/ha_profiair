"""Repair Issues fuer die KWL Fraenkische Rohrwerke Integration.

Erstellt actionable Repair Issues in der HA UI wenn der Filter
gewechselt werden muss oder andere Probleme auftreten.
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.core import HomeAssistant

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
    return ConfirmRepairFlow()


class FilterRepairFlow(RepairsFlow):
    """Repair Flow fuer den Filterwechsel-Alarm.

    Fuehrt den Nutzer durch:
    1. Filter tatsaechlich wechseln
    2. Alarm am Geraet quittieren via button.kwl_filterfehler_bestaetigen
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Erster Schritt -- Nutzer bestaetigt dass Filter gewechselt wurde."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if user_input is not None:
            # Alarm am Geraet quittieren
            # entry_id wird in data mitgegeben beim async_create_issue Aufruf
            entry_id = (self.issue_data or {}).get("entry_id")
            entry = (
                self.hass.config_entries.async_get_entry(entry_id)
                if entry_id else None
            )
            if entry:
                coordinator = entry.runtime_data
                try:
                    url = f"http://{coordinator.host}/filter.cgi?filter=1"
                    session = coordinator._get_session()
                    async with session.get(url) as resp:
                        resp.raise_for_status()
                    await coordinator.async_request_refresh()
                    _LOGGER.info("KWL Filterwechsel-Alarm quittiert")
                except Exception as err:
                    _LOGGER.warning("Fehler beim Quittieren: %s", err)

            return self.async_create_entry(data={})

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={},
        )
