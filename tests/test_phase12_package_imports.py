"""Guard: alle Integrations-Module müssen sich im PAKET-Stil importieren lassen.

Hintergrund (echter CI-Fehler):
Die test_phase*-Suite importiert Module direkt (sys.path zeigt in den
Integrationsordner, dann `import analytics`). Andere Tests importieren im
Paket-Stil (`from kwl_fraenkische.fan import KWLFan`). Nur der zweite Stil
löst die relativen Importe und `__init__.py` aus -- und genau dabei fiel auf,
dass conftests HA-Stubs unvollständig waren:

  - Modul-Stubs waren MagicMock-Objekte. Die funktionieren beim
    `import x as y`-Stil, aber bei `from x.y import Name` geht Pythons
    Import-Maschinerie an ihnen vorbei und liefert frische Auto-Mocks. Die
    HA-Basisklassen wurden dadurch zu MagicMocks
    -> "TypeError: metaclass conflict" beim class-Statement.
  - `_EntityDescription` war eine schlichte Klasse statt eines Dataclass.
    Die Integration erbt davon mit @dataclass(frozen=True, kw_only=True);
    ohne Dataclass-Basis werden keine Felder vererbt
    -> "unexpected keyword argument 'key'" bzw.
       "Mock object has no attribute '__mro__'".

Beides ist in conftest behoben. Dieser Test hält es so: Bricht ein Stub
erneut, schlägt er hier fehl, statt erst in CI in einer anderen Testdatei.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# custom_components/ auf den Pfad -- ermöglicht `import kwl_fraenkische.<modul>`
_CC = Path(__file__).resolve().parent.parent / "custom_components"
if str(_CC) not in sys.path:
    sys.path.insert(0, str(_CC))

PLATFORM_MODULES = [
    "kwl_fraenkische.fan",
    "kwl_fraenkische.sensor",
    "kwl_fraenkische.binary_sensor",
    "kwl_fraenkische.select",
    "kwl_fraenkische.number",
    "kwl_fraenkische.button",
    "kwl_fraenkische.repairs",
    "kwl_fraenkische.config_flow",
    "kwl_fraenkische.diagnostics",
    "kwl_fraenkische.coordinator",
    "kwl_fraenkische.flex_coordinator",
]


@pytest.mark.parametrize("module_name", PLATFORM_MODULES)
def test_module_imports_package_style(module_name: str):
    """Muss ohne metaclass-conflict / dataclass-Fehler importierbar sein."""
    mod = importlib.import_module(module_name)
    assert mod is not None


def test_entity_description_base_is_dataclass():
    """Die EntityDescription-Basis muss ein Dataclass sein, sonst erben die
    Description-Subklassen der Integration keine Felder (key, name, icon ...)."""
    import dataclasses

    from homeassistant.components.sensor import SensorEntityDescription

    assert dataclasses.is_dataclass(SensorEntityDescription), (
        "SensorEntityDescription-Stub muss ein Dataclass sein"
    )


def test_description_accepts_standard_fields():
    """Ein Description-Objekt der Integration muss mit den HA-Standardfeldern
    konstruierbar sein -- genau das schlug mit der alten Stub-Basis fehl."""
    from kwl_fraenkische.sensor import KWLSensorDescription

    d = KWLSensorDescription(key="probe", name="Probe", icon="mdi:test")
    assert d.key == "probe"
    assert d.name == "Probe"


def test_base_classes_are_real_classes():
    """FanEntity/CoordinatorEntity müssen echte Klassen sein (keine MagicMocks),
    sonst scheitert jedes class-Statement mit metaclass conflict."""
    from homeassistant.components.fan import FanEntity
    from homeassistant.helpers.update_coordinator import CoordinatorEntity

    assert isinstance(FanEntity, type), "FanEntity-Stub ist keine echte Klasse"
    assert isinstance(CoordinatorEntity, type), (
        "CoordinatorEntity-Stub ist keine echte Klasse"
    )
