"""Tests für den energy_total-Gesamtsensor (UX-Roadmap 2.1).

Aggregiert die vier energy_level_X-Werte zu einem Gesamtverbrauch für das
HA Energy Dashboard, statt den Nutzer vier Sensoren manuell addieren zu lassen.

Wichtigster Fall: None-Toleranz -- fehlt der Stundenwert einzelner Stufen
(z.B. Tag noch nicht erreicht), darf der Gesamtwert trotzdem aus den
vorhandenen Stufen gebildet werden, nicht komplett None werden.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(
    0, str(Path(__file__).parent.parent / "custom_components" / "kwl_fraenkische")
)


def _load_helper():
    """Lädt _energy_total_kwh isoliert, ohne den vollen HA-Sensor-Import.

    sensor.py importiert HA-Module, die im Stub nicht da sind -- daher die
    Funktion gezielt aus dem Quelltext extrahieren und mit dem _energy_kwh-
    Helper in einem Mini-Namespace ausführen.
    """
    import ast, textwrap
    src = open(
        Path(__file__).parent.parent
        / "custom_components" / "kwl_fraenkische" / "sensor.py"
    ).read()
    tree = ast.parse(src)
    wanted = {"_energy_kwh", "_energy_total_kwh"}
    funcs = [
        ast.get_source_segment(src, node)
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    ns: dict = {"LEVEL_TO_WATT": {1: 11.0, 2: 17.5, 3: 43.5, 4: 80.0}, "Any": object}
    exec("\n\n".join(funcs), ns)
    return ns["_energy_total_kwh"]


_energy_total = _load_helper()


def _data(h1, h2, h3, h4):
    return SimpleNamespace(
        hours_level_1=h1, hours_level_2=h2, hours_level_3=h3, hours_level_4=h4
    )


class TestEnergyTotal:
    def test_sums_all_four_levels(self):
        # 100h@11W + 100h@17.5W + 100h@43.5W + 100h@80W
        # = 1.1 + 1.75 + 4.35 + 8.0 = 15.2 kWh
        result = _energy_total(_data(100, 100, 100, 100))
        assert result == pytest.approx(15.2, abs=0.01)

    def test_tolerates_missing_levels(self):
        """Fehlt eine Stufe (None), zählt die Summe der vorhandenen weiter."""
        # nur Stufe 1+3: 1.1 + 4.35 = 5.45
        result = _energy_total(_data(100, None, 100, None))
        assert result == pytest.approx(5.45, abs=0.01)

    def test_all_none_returns_none(self):
        """Keine einzige Stufe mit Daten → None (nicht 0)."""
        assert _energy_total(_data(None, None, None, None)) is None

    def test_matches_real_device_values(self):
        """Reale 400-touch-Werte aus den Energie-Sensoren des Nutzers:
        1480.77 + 291.51 + 1521.5 + 10.24 = 3304.02 kWh."""
        # Rückgerechnet auf Stunden: kWh * 1000 / watt
        h1 = round(1480.77 * 1000 / 11.0)
        h2 = round(291.51 * 1000 / 17.5)
        h3 = round(1521.5 * 1000 / 43.5)
        h4 = round(10.24 * 1000 / 80.0)
        total = _energy_total(_data(h1, h2, h3, h4))
        # Summe innerhalb Rundungstoleranz der Stundenkonversion
        assert total == pytest.approx(3304.0, abs=1.0)


class TestEnergyTotalSensorDefinition:
    """Strukturelle Prüfung der Sensor-Description via Quelltext."""

    def _src(self) -> str:
        return open(
            Path(__file__).parent.parent
            / "custom_components" / "kwl_fraenkische" / "sensor.py"
        ).read()

    def test_energy_total_is_total_increasing(self):
        src = self._src()
        idx = src.find('key="energy_total"')
        assert idx >= 0, "energy_total Sensor fehlt"
        block = src[idx:idx + 500]
        assert "TOTAL_INCREASING" in block, "Energy Dashboard braucht TOTAL_INCREASING"
        assert "SensorDeviceClass.ENERGY" in block
        assert "KILO_WATT_HOUR" in block

    def test_energy_total_http_only(self):
        src = self._src()
        idx = src.find('key="energy_total"')
        block = src[idx:idx + 700]
        assert "PROTOCOL_HTTP" in block, (
            "energy_total basiert auf touch-Betriebsstunden, muss HTTP-only sein"
        )
