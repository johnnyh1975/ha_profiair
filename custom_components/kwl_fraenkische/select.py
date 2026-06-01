"""Select-Entities fuer die KWL-Anlage."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import KWLConfigEntry

from dataclasses import dataclass, field
from typing import Callable

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ENDPOINT_INSTALL, ENDPOINT_WOPLA
from .coordinator import KWLCapabilities, KWLCoordinator, KWLData, _is_supported

PARALLEL_UPDATES = 1

# ---------------------------------------------------------------------------
# Bypass -- setup.htm
# ---------------------------------------------------------------------------

BYPASS_OPTIONS: dict[str, str] = {
    "Manuell offen": "bypa0",
    "Manuell zu": "bypa1",
    "Automatisch": "bypa2",
}

BYPASS_STATUS_MAP: dict[str, str] = {
    "auto: offen": "Automatisch",
    "auto: zu": "Automatisch",
    "man.: offen": "Manuell offen",
    "man.: zu": "Manuell zu",
    "automatisch": "Automatisch",
    "manuell offen": "Manuell offen",
    "manuell zu": "Manuell zu",
}


def _parse_bypass(raw: str) -> str | None:
    normalized = raw.strip().lower()
    for key, option in BYPASS_STATUS_MAP.items():
        if key in normalized:
            return option
    return None


# ---------------------------------------------------------------------------
# Generische Select-Beschreibung fuer install.htm
# ---------------------------------------------------------------------------

@dataclass(frozen=True, kw_only=True)
class KWLSelectDescription(SelectEntityDescription):
    options_map: dict[str, str] | None = field(default=None)   # HA-Option -> POST-Wert
    reverse_map: dict[str, str] | None = field(default=None)   # Geraete-Text -> HA-Option
    post_field: str = ""
    post_url_fn: Callable[[str], str] | None = field(default=None)  # host -> URL
    value_fn: Callable[[KWLData], str | None] = field(default=lambda d: None)
    entity_registry_enabled_default: bool = True
    required_tag: str | None = field(default=None)
    required_endpoint: str | None = field(default=None)
    entity_category: EntityCategory | None = field(default=None)


def _setup_url(host: str) -> str:
    return f"http://{host}/setup.htm"

def _install_url(host: str) -> str:
    return f"http://{host}/install/install.htm"

def _wopla_url(host: str) -> str:
    """Wochenplan-Seite fuer Programm/Handsteuerung."""
    return f"http://{host}/wopla.htm"


SELECTS: tuple[KWLSelectDescription, ...] = (

    # Bypass -- setup.htm
    KWLSelectDescription(
        key="bypass_select",
        name="Bypass Steuerung",
        icon="mdi:valve",
        options=list(BYPASS_OPTIONS.keys()),
        options_map=BYPASS_OPTIONS,
        post_field="bypassSt",
        post_url_fn=_setup_url,
        value_fn=lambda d: _parse_bypass(d.bypass_status),
    ),

    # Haustyp -- install.htm
    KWLSelectDescription(
        key="install_type",
        entity_category=EntityCategory.CONFIG,
        name="Haustyp",
        icon="mdi:home",
        options=["Eigenheim", "Mietwohnung"],
        options_map={"Eigenheim": "0", "Mietwohnung": "1"},
        reverse_map={"eigenheim": "Eigenheim", "mietwohnung": "Mietwohnung"},
        post_field="Install",
        post_url_fn=_install_url,
        value_fn=lambda d: _normalize_install_type(d.install_type),
    ),

    # Vorheizregister -- install.htm
    KWLSelectDescription(
        key="preheater_mode",
        entity_category=EntityCategory.CONFIG,
        name="Vorheizregister Modus",
        icon="mdi:heating-coil",
        options=["Aktiv", "Passiv"],
        options_map={"Aktiv": "1", "Passiv": "0"},
        reverse_map={"aktiv": "Aktiv", "passiv": "Passiv"},
        post_field="VHR",
        post_url_fn=_install_url,
        value_fn=lambda d: _normalize_preheater(d),
    ),

    # Safety Manager -- install.htm
    KWLSelectDescription(
        key="safety_mode",
        entity_category=EntityCategory.CONFIG,
        name="Safety Manager",
        icon="mdi:shield-check",
        options=["Mit", "Ohne"],
        options_map={"Mit": "1", "Ohne": "0"},
        post_field="Safety",
        post_url_fn=_install_url,
        value_fn=lambda d: "Mit" if d.safety_active else "Ohne",
    ),

    # Externe Sensoren Typ 1-4 -- install.htm
    KWLSelectDescription(
        key="ext_sensor_type_1",
        entity_category=EntityCategory.CONFIG,
        name="Ext. Sensor 1 Typ",
        icon="mdi:thermometer-lines",
        options=["Keiner", "Feuchte (%H)", "CO2 (ppm)"],
        options_map={"Keiner": "0", "Feuchte (%H)": "1", "CO2 (ppm)": "2"},
        reverse_map={"nicht aktiv": "Keiner", "none": "Keiner", "%h": "Feuchte (%H)", "ppm": "CO2 (ppm)"},
        post_field="extSensor1",
        post_url_fn=_install_url,
        value_fn=lambda d: _normalize_sensor_type(d.ext_sensor_type_1),
    ),
    KWLSelectDescription(
        key="ext_sensor_type_2",
        entity_category=EntityCategory.CONFIG,
        name="Ext. Sensor 2 Typ",
        icon="mdi:thermometer-lines",
        options=["Keiner", "Feuchte (%H)", "CO2 (ppm)"],
        options_map={"Keiner": "0", "Feuchte (%H)": "1", "CO2 (ppm)": "2"},
        reverse_map={"nicht aktiv": "Keiner", "none": "Keiner", "%h": "Feuchte (%H)", "ppm": "CO2 (ppm)"},
        post_field="extSensor2",
        post_url_fn=_install_url,
        value_fn=lambda d: _normalize_sensor_type(d.ext_sensor_type_2),
    ),
    KWLSelectDescription(
        key="ext_sensor_type_3",
        entity_category=EntityCategory.CONFIG,
        name="Ext. Sensor 3 Typ",
        icon="mdi:thermometer-lines",
        options=["Keiner", "Feuchte (%H)", "CO2 (ppm)"],
        options_map={"Keiner": "0", "Feuchte (%H)": "1", "CO2 (ppm)": "2"},
        reverse_map={"nicht aktiv": "Keiner", "none": "Keiner", "%h": "Feuchte (%H)", "ppm": "CO2 (ppm)"},
        post_field="extSensor3",
        post_url_fn=_install_url,
        value_fn=lambda d: _normalize_sensor_type(d.ext_sensor_type_3),
    ),
    KWLSelectDescription(
        key="ext_sensor_type_4",
        entity_category=EntityCategory.CONFIG,
        name="Ext. Sensor 4 Typ",
        icon="mdi:thermometer-lines",
        options=["Keiner", "Feuchte (%H)", "CO2 (ppm)"],
        options_map={"Keiner": "0", "Feuchte (%H)": "1", "CO2 (ppm)": "2"},
        reverse_map={"nicht aktiv": "Keiner", "none": "Keiner", "%h": "Feuchte (%H)", "ppm": "CO2 (ppm)"},
        post_field="extSensor4",
        post_url_fn=_install_url,
        value_fn=lambda d: _normalize_sensor_type(d.ext_sensor_type_4),
    ),
)


def _normalize_install_type(raw: str) -> str | None:
    r = raw.strip().lower()
    if "eigenheim" in r:
        return "Eigenheim"
    if "miet" in r:
        return "Mietwohnung"
    return None


def _normalize_preheater(d: KWLData) -> str:
    return "Aktiv" if d.preheater_active else "Passiv"


def _normalize_sensor_type(raw: str) -> str:
    r = raw.strip().lower()
    if "nicht aktiv" in r or r == "none" or r == "":
        return "Keiner"
    if "%h" in r or "feuch" in r:
        return "Feuchte (%H)"
    if "ppm" in r or "co2" in r:
        return "CO2 (ppm)"
    return "Keiner"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KWLConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: KWLCoordinator = entry.runtime_data
    caps = coordinator.capabilities
    mac = entry.data.get("mac", entry.entry_id)
    supported = [d for d in SELECTS if caps is None or _is_supported(d, caps)]
    async_add_entities(
        KWLSelect(coordinator, entry, description, mac)
        for description in supported
    )


class KWLSelect(CoordinatorEntity[KWLCoordinator], SelectEntity):
    """Select-Entity fuer einen KWL-Parameter."""

    _attr_has_entity_name = True
    entity_description: KWLSelectDescription

    def __init__(
        self,
        coordinator: KWLCoordinator,
        entry: ConfigEntry,
        description: KWLSelectDescription,
        mac: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{mac}_{description.key}"
        self._attr_device_info = coordinator.device_info
        self._attr_options = description.options
        self._optimistic_option: str | None = None

    def _handle_coordinator_update(self) -> None:
        if (
            self._optimistic_option is not None
            and self.coordinator.data is not None
        ):
            device_option = self.entity_description.value_fn(self.coordinator.data)
            if device_option == self._optimistic_option:
                self._optimistic_option = None
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.coordinator.data is not None

    @property
    def current_option(self) -> str | None:
        if self._optimistic_option is not None:
            return self._optimistic_option
        if not self.available:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_select_option(self, option: str) -> None:
        if not self.entity_description.options_map:
            return
        post_value = self.entity_description.options_map.get(option)
        if post_value is None:
            return

        payload = {self.entity_description.post_field: post_value}
        if self.entity_description.post_url_fn is None:
            return
        url = self.entity_description.post_url_fn(self.coordinator.host)

        # Korrekte Methode je nach Endpunkt -- install.htm benoetigt BasicAuth
        if "install" in url:
            await self.coordinator.async_post_install(payload)
        else:
            await self.coordinator.async_post_setup(payload)

        self._optimistic_option = option
        self.async_write_ha_state()
