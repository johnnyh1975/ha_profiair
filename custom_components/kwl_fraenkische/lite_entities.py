"""Entitäten für profi-air 140/200 lite (REST/JSON, EXPERIMENTELL).

Bewusst klein: nur, was die lokale API des Geräts hergibt. Lüfterdrehzahl,
Volumenstrom, Filter, Bypass und Außen-/Fortlufttemperaturen liefert das Gerät
über diese Schnittstelle nicht (siehe docs/lite-rest.md).

Die Plattform-Module (fan.py, sensor.py, binary_sensor.py) rufen die
``async_setup_lite_*``-Funktionen auf, wenn der Config Entry das Protokoll
``rest`` trägt.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .lite_client import FUNCTION_NAMES, KWLLiteData
from .lite_coordinator import KWLLiteCoordinator

PARALLEL_UPDATES = 1


class _LiteEntity(CoordinatorEntity[KWLLiteCoordinator]):
    """Gemeinsame Basis: Gerät, unique_id, Verfügbarkeit."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: KWLLiteCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.unique_prefix}_{key}"
        self._attr_device_info = coordinator.device_info

    @property
    def available(self) -> bool:
        return bool(self.coordinator.last_update_success) and self.coordinator.data is not None


# ── Fan ───────────────────────────────────────────────────────────────────────

class KWLLiteFan(_LiteEntity, FanEntity):
    """Ein/Aus und Lüftungsfunktion (Auto, Nacht, Min, Max).

    Das Gerät kennt keine Prozent- oder Stufenwerte, nur diese vier Funktionen;
    sie erscheinen als Preset-Modi.
    """

    _attr_name = None
    _attr_translation_key = "lite_fan"
    _attr_supported_features = (
        FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )
    _attr_preset_modes = list(FUNCTION_NAMES)

    def __init__(self, coordinator: KWLLiteCoordinator) -> None:
        super().__init__(coordinator, "fan")
        self.entity_id = f"fan.{coordinator.model_slug}"

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        return None if data is None else data.running

    @property
    def preset_mode(self) -> str | None:
        data = self.coordinator.data
        return None if data is None else data.function

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        if data is None:
            return {}
        return {
            "contact_presence": data.contact_presence,
            "key_lock": data.key_lock,
            "calendar_active": data.calendar_active,
        }

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if preset_mode not in FUNCTION_NAMES:
            return
        await self.coordinator.async_set_function(preset_mode)

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        await self.coordinator.async_set_power(True)
        if preset_mode is not None:
            await self.async_set_preset_mode(preset_mode)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_power(False)


# ── Sensoren ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True, kw_only=True)
class KWLLiteSensorDescription(SensorEntityDescription):
    value_fn: Callable[[KWLLiteData], Any]


LITE_SENSORS: tuple[KWLLiteSensorDescription, ...] = (
    KWLLiteSensorDescription(
        key="room_temperature",
        translation_key="lite_room_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: d.room_temp,
    ),
    KWLLiteSensorDescription(
        key="humidity",
        translation_key="lite_humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.humidity,
    ),
    KWLLiteSensorDescription(
        key="air_quality",
        translation_key="lite_air_quality",
        icon="mdi:air-filter",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.air_quality_level,
    ),
    KWLLiteSensorDescription(
        key="water_temperature",
        translation_key="lite_water_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.water_temp,
    ),
    KWLLiteSensorDescription(
        key="alarms",
        translation_key="lite_alarms",
        icon="mdi:alert-circle-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: ", ".join(d.alarms) if d.alarms else "",
    ),
)


class KWLLiteSensor(_LiteEntity, SensorEntity):
    entity_description: KWLLiteSensorDescription

    def __init__(
        self, coordinator: KWLLiteCoordinator, description: KWLLiteSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self.entity_id = f"sensor.{coordinator.model_slug}_{description.key}"

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data
        return None if data is None else self.entity_description.value_fn(data)


# ── Binärsensoren ─────────────────────────────────────────────────────────────

@dataclass(frozen=True, kw_only=True)
class KWLLiteBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[KWLLiteData], bool]


LITE_BINARY_SENSORS: tuple[KWLLiteBinarySensorDescription, ...] = (
    KWLLiteBinarySensorDescription(
        key="alarm_active",
        translation_key="lite_alarm_active",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:alert-circle",
        value_fn=lambda d: d.has_alarm,
    ),
    KWLLiteBinarySensorDescription(
        key="contact_presence",
        translation_key="lite_contact_presence",
        icon="mdi:window-open-variant",
        value_fn=lambda d: d.contact_presence,
    ),
    KWLLiteBinarySensorDescription(
        key="key_lock",
        translation_key="lite_key_lock",
        icon="mdi:lock",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.key_lock,
    ),
)


class KWLLiteBinarySensor(_LiteEntity, BinarySensorEntity):
    entity_description: KWLLiteBinarySensorDescription

    def __init__(
        self,
        coordinator: KWLLiteCoordinator,
        description: KWLLiteBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self.entity_id = f"binary_sensor.{coordinator.model_slug}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        return None if data is None else self.entity_description.value_fn(data)


# ── Setup-Funktionen für die Plattform-Module ─────────────────────────────────

async def async_setup_lite_fan(
    coordinator: KWLLiteCoordinator, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([KWLLiteFan(coordinator)])


async def async_setup_lite_sensors(
    coordinator: KWLLiteCoordinator, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([KWLLiteSensor(coordinator, d) for d in LITE_SENSORS])


async def async_setup_lite_binary_sensors(
    coordinator: KWLLiteCoordinator, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([KWLLiteBinarySensor(coordinator, d) for d in LITE_BINARY_SENSORS])
