"""Fan-Entity fuer die KWL-Lüftungsanlage."""
from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from . import KWLConfigEntry

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import KWLCoordinator

PARALLEL_UPDATES = 1

PRESET_MODES = {
    "Stufe 1 - Feuchteschutz": 1,
    "Stufe 2 - Reduziert": 2,
    "Stufe 3 - Nennlueftung": 3,
    "Stufe 4 - Intensivlueftung": 4,
}
LEVEL_TO_PRESET = {v: k for k, v in PRESET_MODES.items()}

LEVEL_TO_PERCENT = {1: 25, 2: 50, 3: 75, 4: 100}


def _percent_to_level(percent: int) -> int:
    if percent <= 30:
        return 1
    if percent <= 55:
        return 2
    if percent <= 80:
        return 3
    return 4


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KWLConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: KWLCoordinator = entry.runtime_data
    async_add_entities([KWLFan(coordinator, entry)])


class KWLFan(CoordinatorEntity[KWLCoordinator], FanEntity):
    """Repraesentiert die KWL-Lüftungsanlage als Fan-Entity.

    Die KWL laeuft immer -- es gibt kein echtes Ausschalten.
    Deshalb wird FanEntityFeature.TURN_OFF bewusst NICHT gesetzt.
    HA zeigt dann keinen Ein/Aus-Schalter an und ruft async_turn_off
    niemals auf. Stufe und Prozent sind die einzigen Steueroptions.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "kwl_fan"
    _attr_supported_features = (
        FanEntityFeature.PRESET_MODE
        | FanEntityFeature.SET_SPEED
        | FanEntityFeature.TURN_ON
        # TURN_OFF bewusst weggelassen -- KWL kann nicht abgeschaltet werden
    )
    _attr_preset_modes = list(PRESET_MODES.keys())
    _attr_speed_count = 4

    def __init__(self, coordinator: KWLCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        mac = entry.data.get("mac", entry.entry_id)
        self._attr_unique_id = f"{mac}_fan"
        self._attr_device_info = coordinator.device_info
        self._optimistic_level: int | None = None

    def _handle_coordinator_update(self) -> None:
        if (
            self._optimistic_level is not None
            and self.coordinator.data is not None
            and self.coordinator.data.current_level == self._optimistic_level
        ):
            self._optimistic_level = None
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.coordinator.data is not None

    @property
    def _current_level(self) -> int:
        if self._optimistic_level is not None:
            return self._optimistic_level
        if self.coordinator.data is not None:
            return int(self.coordinator.data.current_level)
        return 1

    @property
    def is_on(self) -> bool:
        """KWL laeuft immer -- kein echter Aus-Zustand."""
        return True

    @property
    def percentage(self) -> int | None:
        if not self.available and self._optimistic_level is None:
            return None
        return LEVEL_TO_PERCENT.get(self._current_level)

    @property
    def preset_mode(self) -> str | None:
        if not self.available and self._optimistic_level is None:
            return None
        return LEVEL_TO_PRESET.get(self._current_level)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Nur Attribute die nicht bereits als separate Sensoren verfuegbar sind."""
        attrs: dict[str, object] = {
            "leistung_watt": self.coordinator.watt_map.get(self._current_level),
        }
        if self._optimistic_level is not None:
            attrs["optimistic"] = True
        return attrs

    async def _set_level(self, level: int) -> None:
        self._optimistic_level = level
        self.async_write_ha_state()
        await self.coordinator.async_set_level(level)

    async def async_set_percentage(self, percentage: int) -> None:
        # percentage=0 auf Stufe 1 mappen statt abschalten
        level = 1 if percentage == 0 else _percent_to_level(percentage)
        await self._set_level(level)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        level = PRESET_MODES.get(preset_mode)
        if level is None:
            return
        await self._set_level(level)

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: object,
    ) -> None:
        if preset_mode is not None:
            await self.async_set_preset_mode(preset_mode)
        elif percentage is not None:
            await self.async_set_percentage(percentage)
        else:
            await self._set_level(1)
