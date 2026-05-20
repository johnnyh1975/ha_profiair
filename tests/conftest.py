"""Pytest-Fixtures fuer die KWL-Integration Tests."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, AsyncMock
import pytest

# ── HA komplett mocken BEVOR irgendwelche Integration-Module importiert werden
# Basis-Klassen muessen echte Python-Klassen sein damit Vererbung funktioniert

class MockEntity:
    """Basis-Mock fuer HA Entities."""
    _attr_has_entity_name = False
    _attr_unique_id = None
    _attr_device_info = None
    _attr_force_update = False
    _attr_entity_registry_enabled_default = True

    def async_write_ha_state(self): pass

class MockCoordinatorEntity(MockEntity):
    def __init__(self, coordinator):
        self.coordinator = coordinator
    def _handle_coordinator_update(self): pass

    def __class_getitem__(cls, item):
        return cls

class MockFanEntity(MockEntity): pass
class MockSensorEntity(MockEntity): pass
class MockBinarySensorEntity(MockEntity): pass
class MockNumberEntity(MockEntity): pass
class MockSelectEntity(MockEntity): pass
class MockButtonEntity(MockEntity): pass

class MockDataUpdateCoordinator:
    def __init__(self, hass, logger, *, name, update_interval, config_entry=None):
        self.hass = hass
        self.data = None
        self.last_update_success = True
        self.update_interval = update_interval

    def __class_getitem__(cls, item):
        return cls

from dataclasses import dataclass as _dataclass, field as _field

from typing import Any as _Any

@_dataclass(frozen=True)
class MockEntityDescription:
    """Basis fuer alle EntityDescription Mocks -- simuliert HA EntityDescription."""
    key: str = ""
    name: str = ""
    icon: str = None
    entity_registry_enabled_default: bool = True
    # Sensor
    device_class: _Any = None
    state_class: _Any = None
    native_unit_of_measurement: str = None
    suggested_display_precision: int = None
    # Number
    native_min_value: float = None
    native_max_value: float = None
    native_step: float = None
    mode: _Any = None
    # Select
    options: _Any = None
    # Button (keine extra Felder noetig)

# Mock-Module registrieren
mocks = {
    'homeassistant': MagicMock(),
    'homeassistant.core': MagicMock(),
    'homeassistant.config_entries': MagicMock(ConfigEntry=MagicMock),
    'homeassistant.const': MagicMock(
        CONF_HOST='host', CONF_USERNAME='username', CONF_PASSWORD='password',
        Platform=MagicMock()
    ),
    'homeassistant.exceptions': MagicMock(HomeAssistantError=Exception),
    'homeassistant.components.fan': MagicMock(
        FanEntity=MockFanEntity,
        FanEntityFeature=MagicMock(PRESET_MODE=1, SET_SPEED=2, TURN_ON=4)
    ),
    'homeassistant.components.sensor': MagicMock(
        SensorEntity=MockSensorEntity,
        SensorEntityDescription=MockEntityDescription,
        SensorDeviceClass=MagicMock(),
        SensorStateClass=MagicMock()
    ),
    'homeassistant.components.binary_sensor': MagicMock(
        BinarySensorEntity=MockBinarySensorEntity,
        BinarySensorEntityDescription=MockEntityDescription,
        BinarySensorDeviceClass=MagicMock()
    ),
    'homeassistant.components.number': MagicMock(
        NumberEntity=MockNumberEntity,
        NumberEntityDescription=MockEntityDescription,
        NumberDeviceClass=MagicMock(),
        NumberMode=MagicMock()
    ),
    'homeassistant.components.select': MagicMock(
        SelectEntity=MockSelectEntity,
        SelectEntityDescription=MockEntityDescription
    ),
    'homeassistant.components.button': MagicMock(
        ButtonEntity=MockButtonEntity,
        ButtonEntityDescription=MockEntityDescription
    ),
    'homeassistant.components.repairs': MagicMock(
        ConfirmRepairFlow=object,
        RepairsFlow=object,
        IssueSeverity=MagicMock(),
        async_create_issue=MagicMock(),
        async_delete_issue=MagicMock(),
    ),
    'homeassistant.helpers.update_coordinator': MagicMock(
        DataUpdateCoordinator=MockDataUpdateCoordinator,
        CoordinatorEntity=MockCoordinatorEntity,
        UpdateFailed=Exception
    ),
    'homeassistant.helpers.entity_platform': MagicMock(),
    'homeassistant.helpers.aiohttp_client': MagicMock(),
    'homeassistant.helpers.event': MagicMock(),
    'homeassistant.helpers.device_registry': MagicMock(DeviceInfo=dict),
    'homeassistant.util': MagicMock(),
    'homeassistant.util.dt': MagicMock(),
}

for name, mock in mocks.items():
    sys.modules[name] = mock

# Jetzt Integration importierbar
sys.path.insert(0, '/home/claude/kwl_package/custom_components')


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
</response>"""


@pytest.fixture
def sample_xml():
    return SAMPLE_XML
