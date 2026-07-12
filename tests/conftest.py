"""Test-Infrastruktur: Stub-Module für homeassistant.

Alle Stubs werden hier einmalig registriert, bevor irgendein Produktiv-Modul
importiert wird. Echte Python-Klassen statt MagicMock für alles was als
Basisklasse dient (vermeidet Metaclass-Konflikte bei class-Definitionen).
"""
from __future__ import annotations
import sys
import types
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

# ── Echte Basisklassen ────────────────────────────────────────────────────────

class _Entity:
    _attr_has_entity_name = False
    _attr_name = None
    _attr_translation_key = None
    _attr_unique_id = None
    _attr_device_info = None
    _attr_available = True
    def async_write_ha_state(self): pass

class _CoordinatorEntity(_Entity):
    """Basisklasse mit __class_getitem__ für CoordinatorEntity[T] Syntax."""
    def __init__(self, coordinator, *args, **kwargs):
        self.coordinator = coordinator
    def _handle_coordinator_update(self): pass
    @classmethod
    def __class_getitem__(cls, item):
        return cls

class _FanEntity(_Entity):
    _attr_supported_features = 0
    _attr_preset_modes: list = []
    _attr_speed_count = 0

class _SensorEntity(_Entity): pass
class _BinarySensorEntity(_Entity): pass
class _ButtonEntity(_Entity): pass
class _SelectEntity(_Entity): pass
class _NumberEntity(_Entity): pass

class _DataUpdateCoordinator:
    def __init__(self, *args, **kwargs): pass

class _UpdateFailed(Exception): pass
class _ConfigEntryAuthFailed(Exception): pass

@dataclass(frozen=True, kw_only=True)
class _EntityDescription:
    """Stub fuer HA's EntityDescription -- muss ein FROZEN KW-ONLY DATACLASS sein.

    Die Integration deklariert ihre Description-Subklassen als
    @dataclass(frozen=True, kw_only=True). Ist die Basis eine schlichte Klasse
    (wie zuvor), erbt die Subklasse KEINE Felder, und ein Aufruf mit key=...,
    name=... scheitert mit "unexpected keyword argument 'key'". Nur wenn die
    Basis selbst ein Dataclass ist, werden ihre Felder vererbt.

    Enthalten sind nur HA-Standardfelder; projekteigene Felder (value_fn,
    supported_protocols, attrs_fn, cgi_path, ...) deklarieren die Subklassen
    in der Integration selbst.
    """
    key: str = ""
    name: Any = None
    device_class: Any = None
    state_class: Any = None
    native_unit_of_measurement: Any = None
    suggested_display_precision: Any = None
    icon: Any = None
    entity_category: Any = None
    entity_registry_enabled_default: bool = True
    translation_key: Any = None
    options: Any = None
    native_min_value: Any = None
    native_max_value: Any = None
    native_step: Any = None
    mode: Any = None
    force_update: bool = False

class _AutoMemberMeta(type):
    """Metaklasse fuer Enum-artige HA-Stubs (SensorDeviceClass, Platform, ...).

    Die Integration greift auf viele Enum-Mitglieder zu (VOLTAGE, ENERGY,
    POWER, DIAGNOSTIC, ...). Jedes einzeln im Stub zu pflegen ist Whack-a-Mole:
    ein neuer device_class im Code laesst sonst Tests mit AttributeError
    scheitern, obwohl fachlich nichts kaputt ist. Unbekannte Mitglieder loesen
    sich daher selbst zu ihrem Namen auf; explizit definierte Mitglieder
    behalten ihren Wert.
    """

    def __getattr__(cls, name: str):
        if name.startswith("__"):
            raise AttributeError(name)
        value = name
        setattr(cls, name, value)
        return value


class _Platform(metaclass=_AutoMemberMeta):
    FAN = "fan"
    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"
    NUMBER = "number"
    SELECT = "select"
    BUTTON = "button"

class _FanEntityFeature(metaclass=_AutoMemberMeta):
    PRESET_MODE = 1
    SET_SPEED = 2
    TURN_ON = 4
    TURN_OFF = 8

class _SensorStateClass(metaclass=_AutoMemberMeta):
    MEASUREMENT = "measurement"

class _SensorDeviceClass(metaclass=_AutoMemberMeta):
    TEMPERATURE = "temperature"
    POWER = "power"
    ENERGY = "energy"
    HUMIDITY = "humidity"

class _NumberMode(metaclass=_AutoMemberMeta):
    BOX = "box"
    SLIDER = "slider"

# ── Module stubben ────────────────────────────────────────────────────────────

class _StubModule(types.ModuleType):
    """Echtes Modul-Objekt mit Auto-Attributen.

    Warum nicht einfach MagicMock als Modul (wie zuvor)?
    MagicMock funktioniert nur beim `import x as y`-Stil. Bei
    `from x.y.z import Name` -- und genau so importieren die Integrations-
    Module ihre HA-Basisklassen -- geht Pythons Import-Maschinerie an einem
    MagicMock-Elternmodul vorbei und erzeugt frische Auto-Mocks, statt den in
    sys.modules gepatchten Eintrag zu verwenden. Die Basisklassen werden dann
    zu MagicMocks, was beim Klassen-Statement als "metaclass conflict" und
    beim @dataclass als "Mock object has no attribute '__mro__'" knallt.

    Ein echtes ModuleType-Objekt verhält sich für den Import korrekt. Das
    __getattr__ hier (PEP 562) behält die Bequemlichkeit von MagicMock für
    alle Namen, die nicht ausdrücklich gesetzt werden -- explizit gesetzte
    Basisklassen bleiben echte Python-Klassen.
    """

    def __getattr__(self, name: str):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        m = MagicMock(name=f"{self.__name__}.{name}")
        setattr(self, name, m)
        return m


def _stub(name: str) -> _StubModule:
    m = _StubModule(name)
    m.__path__ = []  # als Paket behandelbar machen
    sys.modules[name] = m
    # Am Elternmodul verankern, damit `from a.b import c` sauber aufloest.
    if "." in name:
        parent_name, _, child = name.rpartition(".")
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, child, m)
    return m

_MODS = [
    "homeassistant", "homeassistant.config_entries", "homeassistant.const",
    "homeassistant.core", "homeassistant.helpers", "homeassistant.helpers.entity_registry",
    "homeassistant.helpers.update_coordinator", "homeassistant.helpers.entity_platform",
    "homeassistant.helpers.entity", "homeassistant.helpers.device_registry",
    "homeassistant.helpers.storage", "homeassistant.helpers.event",
    "homeassistant.helpers.aiohttp_client", "homeassistant.components",
    "homeassistant.components.fan", "homeassistant.components.sensor",
    "homeassistant.components.binary_sensor", "homeassistant.components.button",
    "homeassistant.components.select", "homeassistant.components.number",
    "homeassistant.exceptions", "homeassistant.util", "homeassistant.util.dt",
    # Ergaenzt: werden von repairs.py / config_flow.py importiert.
    "homeassistant.components.repairs", "homeassistant.helpers.issue_registry",
    "homeassistant.helpers.selector",
]
for _m in _MODS:
    if _m not in sys.modules:
        _stub(_m)

# Konkrete Klassen und Konstanten in Stubs einsetzen
import homeassistant.const as _hc
_hc.Platform = _Platform
_hc.CONF_HOST = "host"
_hc.CONF_USERNAME = "username"
_hc.CONF_PASSWORD = "password"
_hc.CONF_SCAN_INTERVAL = "scan_interval"

import homeassistant.helpers.update_coordinator as _coord
_coord.CoordinatorEntity = _CoordinatorEntity
_coord.DataUpdateCoordinator = _DataUpdateCoordinator
_coord.UpdateFailed = _UpdateFailed

import homeassistant.components.fan as _fan
_fan.FanEntity = _FanEntity
_fan.FanEntityFeature = _FanEntityFeature

import homeassistant.components.sensor as _sensor
_sensor.SensorEntity = _SensorEntity
_sensor.SensorEntityDescription = _EntityDescription
_sensor.SensorStateClass = _SensorStateClass
_sensor.SensorDeviceClass = _SensorDeviceClass

import homeassistant.components.binary_sensor as _bs
_bs.BinarySensorEntity = _BinarySensorEntity
_bs.BinarySensorEntityDescription = _EntityDescription
_bs.BinarySensorDeviceClass = MagicMock()

import homeassistant.components.button as _btn
_btn.ButtonEntity = _ButtonEntity
_btn.ButtonEntityDescription = _EntityDescription

import homeassistant.components.select as _sel
_sel.SelectEntity = _SelectEntity
_sel.SelectEntityDescription = _EntityDescription

import homeassistant.components.number as _num
_num.NumberEntity = _NumberEntity
_num.NumberEntityDescription = _EntityDescription
_num.NumberMode = _NumberMode
_num.NumberDeviceClass = MagicMock()

import homeassistant.helpers.entity as _ent
_ent.EntityDescription = _EntityDescription
_ent.DeviceInfo = dict

import homeassistant.helpers.entity_registry as _er
# entity_registry: async_get und async_entries_for_config_entry
# sind Modul-Level-Funktionen (kein MagicMock-Attribut-Problem)
_er.async_get = MagicMock(return_value=MagicMock())
_er.async_entries_for_config_entry = MagicMock(return_value=[])

import homeassistant.helpers.storage as _storage
_storage.Store = MagicMock

import homeassistant.exceptions as _exc
_exc.ConfigEntryAuthFailed = _ConfigEntryAuthFailed

import homeassistant.config_entries as _ce
_ce.ConfigEntry = MagicMock

import homeassistant.helpers.entity_platform as _ep
_ep.AddEntitiesCallback = MagicMock

# DataUpdateCoordinator braucht __class_getitem__ für DataUpdateCoordinator[T] Syntax
class _FakeDataUpdateCoordinator2:
    def __init__(self, *args, **kwargs): pass
    @classmethod
    def __class_getitem__(cls, item):
        return cls

import homeassistant.helpers.update_coordinator as _coord3
_coord3.DataUpdateCoordinator = _FakeDataUpdateCoordinator2

# Selector-Klassen für SelectSelector in Options Flow
class _SelectOptionDict(dict):
    def __init__(self, value=None, label=None):
        super().__init__(value=value, label=label)

class _SelectSelectorConfig:
    def __init__(self, options=None, mode=None, **kwargs):
        self.options = options
        self.mode = mode

class _SelectSelector:
    def __init__(self, config=None):
        self.config = config

if "homeassistant.helpers.selector" not in sys.modules:
    _stub("homeassistant.helpers.selector")
import homeassistant.helpers.selector as _sel_mod
_sel_mod.SelectSelector = _SelectSelector
_sel_mod.SelectSelectorConfig = _SelectSelectorConfig
_sel_mod.SelectOptionDict = _SelectOptionDict




# ── Fixtures (wörtlich aus der urspruenglichen conftest v1.4.0) ─────────
# Diese gingen beim conftest-Neuaufbau fuer die CI verloren; die Legacy-
# Tests (test_capabilities/coordinator/fan/...) haengen daran.
# Wichtig: full_/minimal_capabilities leiten die Tags aus ECHTEM geparstem
# Geraete-XML ab -- nicht aus einer hartkodierten Tag-Liste.
import pytest

SAMPLE_XML = """<response>
  <stufe1>1</stufe1><stufe2>0</stufe2><stufe3>0</stufe3><stufe4>0</stufe4>
  <aktuell0>Stufe1 Feuchteschutz</aktuell0>
  <control0>manuelle Stufenwahl</control0>
  <bypass>Auto: Offen</bypass>
  <partytime>120</partytime>
  <BipaAutAUL> 15.0</BipaAutAUL>
  <BipaAutABL> 22.0</BipaAutABL>
  <abl0> 22.1</abl0><zul0> 19.9</zul0><aul0> 18.8</aul0><fol0> 20.4</fol0>
  <MoStZlUm>1022</MoStZlUm><MoStZlVo>24</MoStZlVo>
  <MoStAlUm>854</MoStAlUm><MoStAlVo>21</MoStAlVo>
  <st1z>24</st1z><st1a>21</st1a>
  <st2z>35</st2z><st2a>32</st2a>
  <st3z>54</st3z><st3a>51</st3a>
  <st4z>68</st4z><st4a>65</st4a>
  <BsSt1>133582</BsSt1><BsSt2>16324</BsSt2>
  <BsSt3>34944</BsSt3><BsSt4>75</BsSt4>
  <BsFs>122</BsFs><BsVhr>0</BsVhr>
  <filtertime>180</filtertime>
  <rest_time>45</rest_time>
  <kor1> 00</kor1><kor2> 00</kor2><kor3> 00</kor3><kor4> 00</kor4>
  <safety>Nicht aktiv </safety>
  <passiv>Aus</passiv>
  <vorheiz>Passiv </vorheiz>
  <installtyp>Eigenheim</installtyp>
  <filter0>Filter ersetzt </filter0>
  <sensortyp1>Nicht aktiv </sensortyp1>
  <sensortyp2>Nicht aktiv </sensortyp2>
  <sensortyp3>Nicht aktiv </sensortyp3>
  <sensortyp4>Nicht aktiv </sensortyp4>
  <S1amb0>0</S1amb0><S2amb0>0</S2amb0><S3amb0>0</S3amb0><S4amb0>0</S4amb0>
  <meldung>HA=Hand </meldung>
  <grundst>Stufe 1 </grundst>
  <nachlauf>5</nachlauf>
  <config_mac>00:04:A3:76:23:66</config_mac>
  <config_ip>10.10.4.1</config_ip>
  <DiIn1>Aus</DiIn1><DiIn2>Aus</DiIn2><DiIn3>Ein</DiIn3>
  <PassivHE> 16.0</PassivHE><PassivHA> 18.0</PassivHA>
  <sensor0>Aus</sensor0>
  <soze>Sommerzeit </soze>
  <time>06:39:06</time>
  <date>Fr, 22.05.2026</date>
  <events>n/a</events>
  <prg1>Stufe 3 </prg1><prg_start1>01:00</prg_start1><prg_stop1>05:00</prg_stop1><prg_wota1>Mo,Di,Mi,Do,Fr,Sa,So</prg_wota1>
  <prg2>Stufe 3 </prg2><prg_start2>13:00</prg_start2><prg_stop2>16:00</prg_stop2><prg_wota2>Mo,Di,Mi,Do,Fr,Sa,So</prg_wota2>
  <prg3>Aus</prg3><prg_start3>13:00</prg_start3><prg_stop3>16:00</prg_stop3><prg_wota3>-</prg_wota3>
  <prg4>Aus</prg4><prg_start4>00:00</prg_start4><prg_stop4>00:00</prg_stop4><prg_wota4>-</prg_wota4>
  <prg5>Aus</prg5><prg_start5>00:00</prg_start5><prg_stop5>00:00</prg_stop5><prg_wota5>-</prg_wota5>
  <prg6>Aus</prg6><prg_start6>00:00</prg_start6><prg_stop6>00:00</prg_stop6><prg_wota6>-</prg_wota6>
  <prg7>Aus</prg7><prg_start7>00:00</prg_start7><prg_stop7>00:00</prg_stop7><prg_wota7>-</prg_wota7>
  <prg8>Aus</prg8><prg_start8>00:00</prg_start8><prg_stop8>00:00</prg_stop8><prg_wota8>-</prg_wota8>
  <prg9>Aus</prg9><prg_start9>00:00</prg_start9><prg_stop9>00:00</prg_stop9><prg_wota9>-</prg_wota9>
  <prg10>Aus</prg10><prg_start10>00:00</prg_start10><prg_stop10>00:00</prg_stop10><prg_wota10>-</prg_wota10>
</response>"""


@pytest.fixture
def sample_xml():
    return SAMPLE_XML


# ── Capability fixtures ───────────────────────────────────────────────────────

MINIMAL_XML = """<response>
  <stufe1>1</stufe1><stufe2>0</stufe2><stufe3>0</stufe3><stufe4>0</stufe4>
  <aktuell0>Stufe1 Feuchteschutz</aktuell0>
  <control0>manuelle Stufenwahl</control0>
  <bypass>Auto: Offen</bypass>
  <partytime>120</partytime>
  <BipaAutAUL> 15.0</BipaAutAUL>
  <BipaAutABL> 22.0</BipaAutABL>
  <abl0> 22.1</abl0><zul0> 19.9</zul0><aul0> 18.8</aul0><fol0> 20.4</fol0>
  <filter0>Filter ersetzt </filter0>
  <filtertime>180</filtertime>
  <rest_time>45</rest_time>
  <SprachWahl>lang1</SprachWahl>
  <config_mac>00:04:A3:76:23:66</config_mac>
  <config_ip>10.10.4.1</config_ip>
  <DiIn1>Aus</DiIn1><DiIn2>Aus</DiIn2><DiIn3>Ein</DiIn3>
  <PassivHE> 16.0</PassivHE><PassivHA> 18.0</PassivHA>
  <sensor0>Aus</sensor0>
  <soze>Sommerzeit </soze>
  <time>06:39:06</time>
  <date>Fr, 22.05.2026</date>
  <events>n/a</events>
  <prg1>Stufe 3 </prg1><prg_start1>01:00</prg_start1><prg_stop1>05:00</prg_stop1><prg_wota1>Mo,Di,Mi,Do,Fr,Sa,So</prg_wota1>
  <prg2>Stufe 3 </prg2><prg_start2>13:00</prg_start2><prg_stop2>16:00</prg_stop2><prg_wota2>Mo,Di,Mi,Do,Fr,Sa,So</prg_wota2>
  <prg3>Aus</prg3><prg_start3>13:00</prg_start3><prg_stop3>16:00</prg_stop3><prg_wota3>-</prg_wota3>
  <prg4>Aus</prg4><prg_start4>00:00</prg_start4><prg_stop4>00:00</prg_stop4><prg_wota4>-</prg_wota4>
  <prg5>Aus</prg5><prg_start5>00:00</prg_start5><prg_stop5>00:00</prg_stop5><prg_wota5>-</prg_wota5>
  <prg6>Aus</prg6><prg_start6>00:00</prg_start6><prg_stop6>00:00</prg_stop6><prg_wota6>-</prg_wota6>
  <prg7>Aus</prg7><prg_start7>00:00</prg_start7><prg_stop7>00:00</prg_stop7><prg_wota7>-</prg_wota7>
  <prg8>Aus</prg8><prg_start8>00:00</prg_start8><prg_stop8>00:00</prg_stop8><prg_wota8>-</prg_wota8>
  <prg9>Aus</prg9><prg_start9>00:00</prg_start9><prg_stop9>00:00</prg_stop9><prg_wota9>-</prg_wota9>
  <prg10>Aus</prg10><prg_start10>00:00</prg_start10><prg_stop10>00:00</prg_stop10><prg_wota10>-</prg_wota10>
</response>"""


@pytest.fixture
def minimal_xml():
    """Minimale status.xml -- Touch-Firmware ohne Motor/Installer etc."""
    return MINIMAL_XML


@pytest.fixture
def full_capabilities():
    """KWLCapabilities fuer voll ausgestattete Firmware (non-Touch)."""
    from kwl_fraenkische.coordinator import KWLCapabilities
    from kwl_fraenkische.const import (
        ALL_KNOWN_TAGS, ENDPOINT_INSTALL, ENDPOINT_TIME, ENDPOINT_WOPLA
    )
    from kwl_fraenkische.coordinator import _parse_xml
    raw = _parse_xml(SAMPLE_XML)
    return KWLCapabilities(
        available_tags=frozenset(raw.keys()),
        unknown_tags=frozenset(),
        reachable_endpoints=frozenset({ENDPOINT_INSTALL, ENDPOINT_TIME, ENDPOINT_WOPLA}),
    )


@pytest.fixture
def minimal_capabilities():
    """KWLCapabilities fuer minimale Firmware (Touch / neuere Version)."""
    from kwl_fraenkische.coordinator import KWLCapabilities, _parse_xml
    from kwl_fraenkische.const import ENDPOINT_WOPLA
    raw = _parse_xml(MINIMAL_XML)
    return KWLCapabilities(
        available_tags=frozenset(raw.keys()),
        unknown_tags=frozenset(),
        reachable_endpoints=frozenset({ENDPOINT_WOPLA}),
    )
