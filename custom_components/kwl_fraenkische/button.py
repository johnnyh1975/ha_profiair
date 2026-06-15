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
from homeassistant.helpers.entity import EntityCategory

from .const import CONF_PROTOCOL, DOMAIN, ENDPOINT_INSTALL, ENDPOINT_WOPLA, PROTOCOL_HTTP, PROTOCOL_MODBUS
from .coordinator import KWLCapabilities, KWLCoordinator, _is_supported

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class KWLButtonDescription(ButtonEntityDescription):
    # GET-Endpunkt relativ zum Host (leer für flex-Buttons)
    cgi_path: str = ""
    required_tag: str | None = field(default=None)
    required_endpoint: str | None = field(default=None)
    entity_category: EntityCategory | None = field(default=None)
    supported_protocols: frozenset[str] | None = field(default=None)


BUTTONS: tuple[KWLButtonDescription, ...] = (
    KWLButtonDescription(
        key="filter_reset",
        name="Filterfehler bestaetigen",
        icon="mdi:air-filter",
        cgi_path="/filter.cgi?filter=1",
        supported_protocols=frozenset({PROTOCOL_HTTP}),
    ),
    KWLButtonDescription(
        key="sensor_toggle",
        name="Externe Sensoren umschalten",
        icon="mdi:thermometer-lines",
        cgi_path="/sensor.cgi?sensor=1",
        supported_protocols=frozenset({PROTOCOL_HTTP}),
    ),

    # ── Flex-only Buttons ─────────────────────────────────────────────────────
    KWLButtonDescription(
        key="filter_reset_flex",
        name="Filterfehler bestaetigen",
        icon="mdi:air-filter",
        supported_protocols=frozenset({PROTOCOL_MODBUS}),
    ),
    KWLButtonDescription(
        key="alarm_clear",
        name="Alarm quittieren",
        icon="mdi:bell-cancel",
        supported_protocols=frozenset({PROTOCOL_MODBUS}),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KWLConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    protocol = entry.data.get(CONF_PROTOCOL, PROTOCOL_HTTP)
    mac = entry.data.get("mac", entry.entry_id)
    entities: list = []

    if protocol == PROTOCOL_MODBUS:
        supported = [
            d for d in BUTTONS
            if d.supported_protocols is None or PROTOCOL_MODBUS in d.supported_protocols
        ]
        entities = [KWLFlexButton(coordinator, entry, d, mac) for d in supported]
        entities.append(KWLAnalyticsResetButton(coordinator, entry, mac))
    else:
        caps = coordinator.capabilities
        supported = [
            d for d in BUTTONS
            if (d.supported_protocols is None or PROTOCOL_HTTP in d.supported_protocols)
            and (caps is None or _is_supported(d, caps))
        ]
        entities = [KWLButton(coordinator, entry, d, mac) for d in supported]
        entities.append(KWLAnalyticsResetButton(coordinator, entry, mac))

    async_add_entities(entities)


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
        if not description.translation_key:
            self._attr_translation_key = description.key
        self.entity_id = f"button.{coordinator.model_slug}_{description.key}"

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


class KWLFlexButton(CoordinatorEntity, ButtonEntity):  # type: ignore[type-arg]
    """Button für Flex-Geräte (Modbus TCP) — ruft Coordinator-Methode auf."""

    _attr_has_entity_name = True
    entity_description: KWLButtonDescription

    def __init__(self, coordinator, entry: ConfigEntry, description: KWLButtonDescription, mac: str) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{mac}_{description.key}"
        self._attr_device_info = coordinator.device_info
        if not description.translation_key:
            self._attr_translation_key = description.key
        self.entity_id = f"button.{coordinator.model_slug}_{description.key}"

    @property
    def available(self) -> bool:
        return bool(self.coordinator.last_update_success)

    async def async_press(self) -> None:
        key = self.entity_description.key
        if key == "filter_reset_flex":
            await self.coordinator.async_reset_filter()
        elif key == "alarm_clear":
            await self.coordinator.async_clear_alarm()


class KWLAnalyticsResetButton(CoordinatorEntity[KWLCoordinator], ButtonEntity):
    """Setzt alle Analytics-Baselines zurueck -- z.B. nach Filterwechsel."""

    _attr_has_entity_name = True
    _attr_name = "Analytics Baselines zuruecksetzen"
    _attr_icon = "mdi:chart-timeline-variant-shimmer"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = True

    def __init__(
        self,
        coordinator: KWLCoordinator,
        entry: ConfigEntry,
        mac: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{mac}_analytics_reset"
        self._attr_device_info = coordinator.device_info
        self._attr_translation_key = "analytics_reset"
        self.entity_id = f"button.{coordinator.model_slug}_analytics_reset"

    @property
    def available(self) -> bool:
        return bool(self.coordinator.last_update_success)

    async def async_press(self) -> None:
        """Analytics-Baselines loeschen und neu aufbauen."""
        await self.coordinator.async_reset_analytics()
