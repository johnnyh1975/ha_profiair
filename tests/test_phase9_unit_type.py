"""Tests für extract_unit_type (System-ID → Gerätetyp).

Regression-Schutz für den Bug "Unknown device type 195": laut offizieller
Fränkische Modbus-Doku (Kap. 4.2.4) liegt der Typ im HIGH-Byte (Byte 4) von
prmSystemID, nicht im Low-Byte. Der alte Code las `sys_id & 0xFF` und scheiterte
auf Firmware 3.22, die im Low-Byte eine Seriennummer ablegt.
"""
import ast
from pathlib import Path

import pytest

FLEX = (
    Path(__file__).parent.parent
    / "custom_components" / "kwl_fraenkische" / "flex_coordinator.py"
)


def _load_extract_unit_type():
    """extract_unit_type isoliert aus dem Quelltext laden (ohne HA-Imports)."""
    src = FLEX.read_text()
    tree = ast.parse(src)
    func_src = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "extract_unit_type":
            func_src = ast.get_source_segment(src, node)
            break
    assert func_src, "extract_unit_type nicht gefunden"
    ns = {"UNIT_TYPE_TO_MODEL": {4: "180_flat", 11: "250_flex", 15: "360_flex"}}
    exec(func_src, ns)
    return ns["extract_unit_type"]


extract_unit_type = _load_extract_unit_type()


class TestExtractUnitType:
    def test_reporter_360_flex_fw322(self):
        """Der reale Reporter-Wert: 360 flex, Firmware 3.22.
        0x0F0035C3 → High-Byte 0x0F = 15 = 360 flex.
        Low-Byte wäre 0xC3 = 195 (der alte Bug)."""
        assert extract_unit_type(0x0F0035C3) == 15

    def test_doc_example_type_4(self):
        """Offizielles Doku-Beispiel (Kap. 4.2.4): 0x040035D3 → Typ 4."""
        assert extract_unit_type(0x040035D3) == 4

    def test_high_byte_250_flex(self):
        assert extract_unit_type(0x0B0012AB) == 11

    def test_legacy_low_byte_fallback(self):
        """Altgerät mit Typ nur im Low-Byte (High-Byte 0) → Fallback greift."""
        assert extract_unit_type(0x0000000F) == 15
        assert extract_unit_type(0x0000000B) == 11
        assert extract_unit_type(0x00000004) == 4

    def test_unknown_returns_high_byte(self):
        """Unbekannter Typ: High-Byte (dokumentierte Position) wird für die
        Fehlermeldung zurückgegeben, nicht das Low-Byte."""
        assert extract_unit_type(0xFF0035C3) == 0xFF

    def test_old_bug_no_longer_reproduces(self):
        """Sicherstellen, dass der alte Low-Byte-Wert 195 NICHT mehr entsteht."""
        assert extract_unit_type(0x0F0035C3) != 195


class TestExtractUnitTypeWiring:
    """Der Helper muss an beiden Stellen genutzt werden (Coordinator + Probe)."""

    def test_coordinator_uses_helper(self):
        src = FLEX.read_text()
        assert "unit_type = extract_unit_type(sys_id)" in src
        # Der alte fehlerhafte Ausdruck darf nicht mehr vorkommen
        assert "unit_type = sys_id & 0xFF" not in src

    def test_config_flow_uses_helper(self):
        cf = (
            Path(__file__).parent.parent
            / "custom_components" / "kwl_fraenkische" / "config_flow.py"
        ).read_text()
        assert "extract_unit_type(sys_id_raw)" in cf
        assert "unit_type = sys_id_raw & 0xFF" not in cf

    def test_docstring_cites_documentation(self):
        """Der Helper muss die dokumentierte Byte-Position belegen (High-Byte),
        damit klar ist, dass dies kein Rateschluss ist."""
        src = FLEX.read_text()
        idx = src.find("def extract_unit_type")
        block = src[idx:idx + 1400]
        assert "Byte 4" in block or ">> 24" in block
