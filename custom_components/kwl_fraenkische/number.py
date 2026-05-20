"""Number-Entities fuer einstellbare Parameter der KWL-Anlage."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import KWLConfigEntry

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfElectricPotential, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import KWLCoordinator, KWLData

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
        name="Bypass Schwelle Aussenluft",
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
        name="Kalibrierung Aussenluft",
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
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KWLConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: KWLCoordinator = entry.runtime_data
    mac = entry.data.get("mac", entry.entry_id)
    async_add_entities(
        KWLNumber(coordinator, entry, description, mac)
        for description in NUMBERS
    )


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
