"""Number-Entities fuer einstellbare Parameter der KWL-Anlage."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import KWLConfigEntry

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import EntityCategory
from homeassistant.const import UnitOfElectricPotential, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_PROTOCOL, DOMAIN, PROTOCOL_HTTP, PROTOCOL_MODBUS
from .coordinator import KWLCapabilities, KWLCoordinator, KWLData, _is_supported

PARALLEL_UPDATES = 1


class Endpoint(Enum):
    SETUP = "setup"
    INSTALL = "install"


@dataclass(frozen=True, kw_only=True)
class KWLNumberDescription(NumberEntityDescription):
    value_fn: Callable[[KWLData], float | None] = lambda d: None
    post_field: str = ""
    endpoint: Endpoint = Endpoint.SETUP
    # Formatierung des POST-Werts
    format_fn: Callable[[float], str] = str
    # Standardmaessig sichtbar? False = nur fuer Experten
    entity_registry_enabled_default: bool = True
    required_tag: str | None = field(default=None)
    required_endpoint: str | None = field(default=None)
    entity_category: EntityCategory | None = field(default=None)
    supported_protocols: frozenset[str] | None = field(default=None)


def _two_digits(v: float) -> str:
    return f"{int(v):02d}"


def _one_decimal(v: float) -> str:
    return f"{v:.1f}"


NUMBERS: tuple[KWLNumberDescription, ...] = (

    # ------------------------------------------------------------------ #
    # setup.htm                                                            #
    # ------------------------------------------------------------------ #

    KWLNumberDescription(
        key="party_timer",
        name="Party-Timer Nachlauf",
        device_class=NumberDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        native_min_value=10,
        native_max_value=240,
        native_step=1,
        mode=NumberMode.BOX,
        endpoint=Endpoint.SETUP,
        post_field="ChangeMinutes",
        format_fn=_two_digits,
        value_fn=lambda d: d.party_timer_minutes,
    ),
    KWLNumberDescription(
        key="bypass_threshold_aul",
        name="Bypass Schwelle Außenluft",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=13,
        native_max_value=18,
        native_step=1,
        mode=NumberMode.SLIDER,
        endpoint=Endpoint.SETUP,
        post_field="ChangeBPAL",
        format_fn=_two_digits,
        value_fn=lambda d: d.bypass_threshold_aul,
    ),
    KWLNumberDescription(
        key="bypass_threshold_abl",
        name="Bypass Schwelle Abluft",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=18,
        native_max_value=25,
        native_step=1,
        mode=NumberMode.SLIDER,
        endpoint=Endpoint.SETUP,
        post_field="ChangeBPAB",
        format_fn=_two_digits,
        value_fn=lambda d: d.bypass_threshold_abl,
    ),

    # ------------------------------------------------------------------ #
    # install.htm -- Temperaturkorrekturen                                 #
    # ------------------------------------------------------------------ #

    KWLNumberDescription(
        key="korrektur_abluft",
        required_tag="kor1",
        name="Kalibrierung Abluft",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=-4.9,
        native_max_value=4.9,
        native_step=0.1,
        mode=NumberMode.BOX,
        endpoint=Endpoint.INSTALL,
        post_field="korrekt1",
        format_fn=_one_decimal,
        value_fn=lambda d: d.korrektur_abluft,
    ),
    KWLNumberDescription(
        key="korrektur_zuluft",
        required_tag="kor2",
        name="Kalibrierung Zuluft",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=-4.9,
        native_max_value=4.9,
        native_step=0.1,
        mode=NumberMode.BOX,
        endpoint=Endpoint.INSTALL,
        post_field="korrekt2",
        format_fn=_one_decimal,
        value_fn=lambda d: d.korrektur_zuluft,
    ),
    KWLNumberDescription(
        key="korrektur_fortluft",
        required_tag="kor3",
        name="Kalibrierung Fortluft",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=-4.9,
        native_max_value=4.9,
        native_step=0.1,
        mode=NumberMode.BOX,
        endpoint=Endpoint.INSTALL,
        post_field="korrekt3",
        format_fn=_one_decimal,
        value_fn=lambda d: d.korrektur_fortluft,
    ),
    KWLNumberDescription(
        key="korrektur_aussenluft",
        required_tag="kor4",
        name="Kalibrierung Außenluft",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=-4.9,
        native_max_value=4.9,
        native_step=0.1,
        mode=NumberMode.BOX,
        endpoint=Endpoint.INSTALL,
        post_field="korrekt4",
        format_fn=_one_decimal,
        value_fn=lambda d: d.korrektur_aussenluft,
    ),

    # ------------------------------------------------------------------ #
    # install.htm -- Luftmenge (Volt pro Stufe)                           #
    # Standardmaessig ausgeblendet -- nur fuer Experten                   #
    # ------------------------------------------------------------------ #

    KWLNumberDescription(
        key="airflow_s1_supply",
        required_tag="st1z",
        name="Luftmenge Stufe 1 Zuluft",
        device_class=NumberDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        native_min_value=0.0,
        native_max_value=10.0,
        native_step=0.1,
        mode=NumberMode.BOX,
        endpoint=Endpoint.INSTALL,
        post_field="ChangeSt1Z",
        format_fn=_one_decimal,
        value_fn=lambda d: d.airflow_s1_supply,
        entity_registry_enabled_default=False,
    ),
    KWLNumberDescription(
        key="airflow_s1_exhaust",
        required_tag="st1a",
        name="Luftmenge Stufe 1 Abluft",
        device_class=NumberDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        native_min_value=0.0,
        native_max_value=10.0,
        native_step=0.1,
        mode=NumberMode.BOX,
        endpoint=Endpoint.INSTALL,
        post_field="ChangeSt1A",
        format_fn=_one_decimal,
        value_fn=lambda d: d.airflow_s1_exhaust,
        entity_registry_enabled_default=False,
    ),
    KWLNumberDescription(
        key="airflow_s2_supply",
        required_tag="st1z",
        name="Luftmenge Stufe 2 Zuluft",
        device_class=NumberDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        native_min_value=0.0,
        native_max_value=10.0,
        native_step=0.1,
        mode=NumberMode.BOX,
        endpoint=Endpoint.INSTALL,
        post_field="ChangeSt2Z",
        format_fn=_one_decimal,
        value_fn=lambda d: d.airflow_s2_supply,
        entity_registry_enabled_default=False,
    ),
    KWLNumberDescription(
        key="airflow_s2_exhaust",
        required_tag="st2a",
        name="Luftmenge Stufe 2 Abluft",
        device_class=NumberDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        native_min_value=0.0,
        native_max_value=10.0,
        native_step=0.1,
        mode=NumberMode.BOX,
        endpoint=Endpoint.INSTALL,
        post_field="ChangeSt2A",
        format_fn=_one_decimal,
        value_fn=lambda d: d.airflow_s2_exhaust,
        entity_registry_enabled_default=False,
    ),
    KWLNumberDescription(
        key="airflow_s3_supply",
        required_tag="st1z",
        name="Luftmenge Stufe 3 Zuluft",
        device_class=NumberDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        native_min_value=0.0,
        native_max_value=10.0,
        native_step=0.1,
        mode=NumberMode.BOX,
        endpoint=Endpoint.INSTALL,
        post_field="ChangeSt3Z",
        format_fn=_one_decimal,
        value_fn=lambda d: d.airflow_s3_supply,
        entity_registry_enabled_default=False,
    ),
    KWLNumberDescription(
        key="airflow_s3_exhaust",
        required_tag="st3a",
        name="Luftmenge Stufe 3 Abluft",
        device_class=NumberDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        native_min_value=0.0,
        native_max_value=10.0,
        native_step=0.1,
        mode=NumberMode.BOX,
        endpoint=Endpoint.INSTALL,
        post_field="ChangeSt3A",
        format_fn=_one_decimal,
        value_fn=lambda d: d.airflow_s3_exhaust,
        entity_registry_enabled_default=False,
    ),
    KWLNumberDescription(
        key="airflow_s4_supply",
        required_tag="st1z",
        name="Luftmenge Stufe 4 Zuluft",
        device_class=NumberDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        native_min_value=0.0,
        native_max_value=10.0,
        native_step=0.1,
        mode=NumberMode.BOX,
        endpoint=Endpoint.INSTALL,
        post_field="ChangeSt4Z",
        format_fn=_one_decimal,
        value_fn=lambda d: d.airflow_s4_supply,
        entity_registry_enabled_default=False,
    ),
    KWLNumberDescription(
        key="airflow_s4_exhaust",
        required_tag="st4a",
        name="Luftmenge Stufe 4 Abluft",
        device_class=NumberDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        native_min_value=0.0,
        native_max_value=10.0,
        native_step=0.1,
        mode=NumberMode.BOX,
        endpoint=Endpoint.INSTALL,
        post_field="ChangeSt4A",
        format_fn=_one_decimal,
        value_fn=lambda d: d.airflow_s4_exhaust,
        entity_registry_enabled_default=False,
    ),

    # ── Flex-only Numbers (profi-air 250/360 flex, 180 flat) ──────────────────
    KWLNumberDescription(
        key="filter_total_days_flex",
        name="Filterintervall",
        device_class=NumberDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.DAYS,
        native_min_value=30,
        native_max_value=360,
        native_step=1,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda d: float(d.filter_total_days) if d.filter_total_days is not None else None,
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

    if protocol == PROTOCOL_MODBUS:
        # Alle existing Numbers haben post_field → HTTP POST → auto-ausgeschlossen
        supported = [
            d for d in NUMBERS
            if (d.supported_protocols is None or PROTOCOL_MODBUS in d.supported_protocols)
            and not d.post_field
            and not d.required_tag
            and not d.required_endpoint
        ]
        async_add_entities(
            KWLFlexNumber(coordinator, entry, d, mac) for d in supported
        )
    else:
        caps = coordinator.capabilities
        supported = [
            d for d in NUMBERS
            if (d.supported_protocols is None or PROTOCOL_HTTP in d.supported_protocols)
            and (caps is None or _is_supported(d, caps))
        ]
        async_add_entities(
            KWLNumber(coordinator, entry, d, mac) for d in supported
        )


class KWLFlexNumber(CoordinatorEntity, NumberEntity):  # type: ignore[type-arg]
    """Numerischer Parameter für Flex-Geräte (Modbus TCP)."""

    _attr_has_entity_name = True
    entity_description: KWLNumberDescription

    def __init__(self, coordinator, entry: ConfigEntry, description: KWLNumberDescription, mac: str) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{mac}_{description.key}"
        self._attr_device_info = coordinator.device_info
        self._attr_entity_registry_enabled_default = description.entity_registry_enabled_default
        if description.entity_category is not None:
            self._attr_entity_category = description.entity_category
        self.entity_id = f"number.{coordinator.model_slug}_{description.key}"

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.coordinator.data is not None

    @property
    def native_value(self) -> float | None:
        if not self.available:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_set_native_value(self, value: float) -> None:
        key = self.entity_description.key
        if key == "filter_total_days_flex":
            await self.coordinator.async_set_filter_total(int(value))


class KWLNumber(CoordinatorEntity[KWLCoordinator], NumberEntity):
    """Einstellbarer numerischer Parameter der KWL-Anlage."""

    _attr_has_entity_name = True
    entity_description: KWLNumberDescription

    def __init__(
        self,
        coordinator: KWLCoordinator,
        entry: ConfigEntry,
        description: KWLNumberDescription,
        mac: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{mac}_{description.key}"
        self._attr_device_info = coordinator.device_info
        self._attr_entity_registry_enabled_default = description.entity_registry_enabled_default
        self.entity_id = f"number.{coordinator.model_slug}_{description.key}"
        self._optimistic_value: float | None = None

    def _handle_coordinator_update(self) -> None:
        if (
            self._optimistic_value is not None
            and self.coordinator.data is not None
        ):
            device_val = self.entity_description.value_fn(self.coordinator.data)
            # Float-sicherer Vergleich -- verhindert Probleme bei Dezimalwerten
            # wie Temperaturkorrekturen (z.B. 0.1 != 0.10000000000000001)
            if device_val is not None and abs(device_val - self._optimistic_value) < 0.05:
                self._optimistic_value = None
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.coordinator.data is not None

    @property
    def native_value(self) -> float | None:
        if self._optimistic_value is not None:
            return self._optimistic_value
        if not self.available:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_set_native_value(self, value: float) -> None:
        formatted = self.entity_description.format_fn(value)
        payload = {self.entity_description.post_field: formatted}

        if self.entity_description.endpoint == Endpoint.SETUP:
            await self.coordinator.async_post_setup(payload)
        else:
            await self.coordinator.async_post_install(payload)

        self._optimistic_value = value
        self.async_write_ha_state()
