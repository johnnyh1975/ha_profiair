"""Test-Infrastruktur: Stub-Module für homeassistant.

Alle Stubs werden hier einmalig registriert, bevor irgendein Produktiv-Modul
importiert wird. Echte Python-Klassen statt MagicMock für alles was als
Basisklasse dient (vermeidet Metaclass-Konflikte bei class-Definitionen).
"""
from __future__ import annotations
import sys
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

class _EntityDescription:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

class _Platform:
    FAN = "fan"
    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"
    NUMBER = "number"
    SELECT = "select"
    BUTTON = "button"

class _FanEntityFeature:
    PRESET_MODE = 1
    SET_SPEED = 2
    TURN_ON = 4
    TURN_OFF = 8

class _SensorStateClass:
    MEASUREMENT = "measurement"

class _SensorDeviceClass:
    TEMPERATURE = "temperature"
    POWER = "power"
    ENERGY = "energy"
    HUMIDITY = "humidity"

class _NumberMode:
    BOX = "box"
    SLIDER = "slider"

# ── Module stubben ────────────────────────────────────────────────────────────

def _stub(name: str) -> MagicMock:
    m = MagicMock(name=name)
    sys.modules[name] = m
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
