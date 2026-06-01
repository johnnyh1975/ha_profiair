"""Button-Entities fuer Einmalaktionen der KWL-Anlage."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import KWLConfigEntry

from dataclasses import dataclass, field

import aiohttp
from homeassistant.exceptions import HomeAssistantError

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ENDPOINT_INSTALL, ENDPOINT_WOPLA
from .coordinator import KWLCapabilities, KWLCoordinator, _is_supported

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class KWLButtonDescription(ButtonEntityDescription):
    # GET-Endpunkt relativ zum Host
    cgi_path: str = ""


BUTTONS: tuple[KWLButtonDescription, ...] = (
    KWLButtonDescription(
        key="filter_reset",
        name="Filterfehler bestaetigen",
        icon="mdi:air-filter",
        cgi_path="/filter.cgi?filter=1",
    ),
    KWLButtonDescription(
        key="sensor_toggle",
        name="Externe Sensoren umschalten",
        icon="mdi:thermometer-lines",
        cgi_path="/sensor.cgi?sensor=1",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KWLConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: KWLCoordinator = entry.runtime_data
    caps = coordinator.capabilities
    mac = entry.data.get("mac", entry.entry_id)
    supported = [d for d in BUTTONS if caps is None or _is_supported(d, caps)]
    async_add_entities(
        KWLButton(coordinator, entry, description, mac)
        for description in supported
    )


class KWLButton(CoordinatorEntity[KWLCoordinator], ButtonEntity):
    """Einmalaktion per GET-Request an die KWL-Anlage."""

    _attr_has_entity_name = True
    entity_description: KWLButtonDescription

    def __init__(
        self,
        coordinator: KWLCoordinator,
        entry: ConfigEntry,
        description: KWLButtonDescription,
        mac: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{mac}_{description.key}"
        self._attr_device_info = coordinator.device_info

    @property
    def available(self) -> bool:
        return bool(self.coordinator.last_update_success)

    async def async_press(self) -> None:
        """GET-Request ausfuehren und danach Coordinator aktualisieren."""
        url = f"http://{self.coordinator.host}{self.entity_description.cgi_path}"
        try:
            session = self.coordinator._get_session()
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                resp.raise_for_status()
        except aiohttp.ClientError as err:
            raise HomeAssistantError(
                f"Fehler beim Ausfuehren von {self.entity_description.key}: {err}"
            ) from err

        # Status sofort neu laden (z.B. filter0 aendert sich nach Quittierung)
        await self.coordinator.async_request_refresh()
