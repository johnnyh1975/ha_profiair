"""Binary Sensor-Entities fuer die KWL-Lüftungsanlage."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import KWLConfigEntry

from dataclasses import dataclass, field
from typing import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import KWLCapabilities, KWLCoordinator, KWLData, _is_supported

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class KWLBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[KWLData], bool | None] = lambda d: None
    required_tag: str | None = field(default=None)
    required_endpoint: str | None = field(default=None)
    entity_category: EntityCategory | None = field(default=None)


@dataclass(frozen=True, kw_only=True)
class KWLAnalyticsBinarySensorDescription(BinarySensorEntityDescription):
    """Description for binary sensors backed by KWLAnalytics."""
    value_fn: Callable[[KWLCoordinator], bool | None] = lambda c: None
    entity_category: EntityCategory | None = field(default=EntityCategory.DIAGNOSTIC)


BINARY_SENSORS: tuple[KWLBinarySensorDescription, ...] = (
    KWLBinarySensorDescription(
        key="filter_ok",
        name="Filter OK",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda d: not d.filter_ok,
    ),
    KWLBinarySensorDescription(
        key="safety_active",
        entity_category=EntityCategory.DIAGNOSTIC,
        required_tag="safety",
        name="Safety Manager",
        device_class=BinarySensorDeviceClass.SAFETY,
        value_fn=lambda d: d.safety_active,
    ),
    KWLBinarySensorDescription(
        key="passive_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        required_tag="passiv",
        name="Passivhaus-Modus",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda d: d.passive_mode,
    ),
    KWLBinarySensorDescription(
        key="preheater_active",
        entity_category=EntityCategory.DIAGNOSTIC,
        required_tag="vorheiz",
        name="Vorheizregister aktiv",
        device_class=BinarySensorDeviceClass.HEAT,
        value_fn=lambda d: d.preheater_active,
    ),

    # ── Diagnose Binary Sensoren ──────────────────────────────────────────────
    KWLBinarySensorDescription(
        key="digital_input_1",
        name="Digitaleingang 1",
        icon="mdi:electric-switch",
        required_tag="DiIn1",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.digital_input_1,
    ),
    KWLBinarySensorDescription(
        key="digital_input_2",
        name="Digitaleingang 2",
        icon="mdi:electric-switch",
        required_tag="DiIn2",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.digital_input_2,
    ),
    KWLBinarySensorDescription(
        key="digital_input_3",
        name="Digitaleingang 3",
        icon="mdi:electric-switch",
        required_tag="DiIn3",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.digital_input_3,
    ),

    # ── Safety / Passiv / Vorheiz (entity_category ergaenzen) ─────────────────
    # (bereits im Tuple -- entity_category ergaenzen via Dataclass field)

    # ── Derived Binary Sensoren ──────────────────────────────────────────────
    KWLBinarySensorDescription(
        key="frost_risk",
        name="Frost-Risiko",
        device_class=BinarySensorDeviceClass.COLD,
        icon="mdi:snowflake-alert",
        required_tag="aul0",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.frost_risk,
    ),
    KWLBinarySensorDescription(
        key="bypass_leaking",
        name="Bypass Leckage",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:valve-open",
        required_tag="fol0",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.bypass_leaking,
    ),
    KWLBinarySensorDescription(
        key="motor_asymmetry",
        name="Motor Asymmetrie",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:fan-alert",
        required_tag="MoStZlUm",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.motor_asymmetry,
    ),
    KWLBinarySensorDescription(
        key="bypass_recommended",
        name="Bypass Vorkuehlung empfohlen",
        icon="mdi:thermometer-chevron-down",
        required_tag="aul0",
        value_fn=lambda d: d.bypass_recommended,
    ),
)

# ── Analytics-backed binary sensors ───────────────────────────────────────────
# These read from coordinator.analytics (KWLAnalytics) rather than KWLData.
# All are disabled by default; they become meaningful once baselines establish.

ANALYTICS_BINARY_SENSORS: tuple[KWLAnalyticsBinarySensorDescription, ...] = (
    KWLAnalyticsBinarySensorDescription(
        key="bypass_hunting",
        name="Bypass Pendeln",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:valve-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.analytics.bypass_hunting if c.analytics else None,
    ),
    KWLAnalyticsBinarySensorDescription(
        key="rpm_anomaly",
        name="Motor RPM Anomalie",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:fan-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.analytics.rpm_anomaly if c.analytics else None,
    ),
    KWLAnalyticsBinarySensorDescription(
        key="ratio_anomaly",
        name="Motor Asymmetrie Trend",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:fan-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.analytics.ratio_anomaly if c.analytics else None,
    ),
    KWLAnalyticsBinarySensorDescription(
        key="eta_below_baseline",
        name="WRG unter Referenzwert",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:heat-wave",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.analytics.eta_below_baseline if c.analytics else None,
    ),
    KWLAnalyticsBinarySensorDescription(
        key="fan_law_anomaly",
        name="EC-Modell Abweichung",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:fan-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: (
            # Residual > ±5% von P_Stufe4 → Messfehler oder Motoranomalie
            # Zwei-Parameter-Modell berücksichtigt ~9W EC-Festanteil korrekt
            any(abs(v) > 5.0 for v in (c.fan_law_consistency or {}).values())
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KWLConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: KWLCoordinator = entry.runtime_data
    mac = entry.data.get("mac", entry.entry_id)
    caps = coordinator.capabilities
    supported = [d for d in BINARY_SENSORS if caps is None or _is_supported(d, caps)]
    entities: list = [
        KWLBinarySensor(coordinator, entry, description, mac)
        for description in supported
    ]
    # Analytics sensors are always added (not capability-gated)
    entities += [
        KWLAnalyticsBinarySensor(coordinator, entry, description, mac)
        for description in ANALYTICS_BINARY_SENSORS
    ]
    async_add_entities(entities)


class KWLBinarySensor(CoordinatorEntity[KWLCoordinator], BinarySensorEntity):
    """Binaerer Sensor aus der KWL-Anlage."""

    _attr_has_entity_name = True
    entity_description: KWLBinarySensorDescription

    def __init__(
        self,
        coordinator: KWLCoordinator,
        entry: ConfigEntry,
        description: KWLBinarySensorDescription,
        mac: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{mac}_{description.key}"
        self._attr_device_info = coordinator.device_info
        # Activate translation lookup from strings.json / translations/*.json
        if not description.translation_key:
            self._attr_translation_key = description.key

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.coordinator.data is not None

    @property
    def is_on(self) -> bool | None:
        """None wenn unavailable -- HA zeigt Entity dann als unavailable an."""
        if not self.available:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class KWLAnalyticsBinarySensor(CoordinatorEntity[KWLCoordinator], BinarySensorEntity):
    """Binary sensor backed by KWLAnalytics (not raw device data)."""

    _attr_has_entity_name = True
    entity_description: KWLAnalyticsBinarySensorDescription

    def __init__(
        self,
        coordinator: KWLCoordinator,
        entry: ConfigEntry,
        description: KWLAnalyticsBinarySensorDescription,
        mac: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{mac}_{description.key}"
        self._attr_device_info = coordinator.device_info
        if description.entity_category is not None:
            self._attr_entity_category = description.entity_category
        if not description.translation_key:
            self._attr_translation_key = description.key

    @property
    def available(self) -> bool:
        return (
            self.coordinator.last_update_success
            and self.coordinator.analytics is not None
        )

    @property
    def is_on(self) -> bool | None:
        if not self.available:
            return None
        return self.entity_description.value_fn(self.coordinator)
