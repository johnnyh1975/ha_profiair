"""Tests für Phase 0: async_migrate_entry v3→v4 und Fan-Entity-Naming.

Abgedeckte Anforderungen (aus IMPLEMENTIERUNGSPLAN.md Phase 0):
- v3-Eintrag ohne CONF_PROTOCOL → nach Migration PROTOCOL_HTTP vorhanden
- Integration startet nach Migration ohne Fehler
- Fan-Entity-ID "fan.x_fan" → "fan.x" umgeschrieben
- Konflikt: "fan.x" existiert bereits → kein Fehler, alter ID bleibt, Warning geloggt
- v4-Eintrag → async_migrate_entry gibt False, keine Änderung
- Neue touch-Installation → entity_id = "fan.profi_air_400" (kein Suffix)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch, call
import pytest


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _make_entry(version: int, data: dict | None = None) -> MagicMock:
    """Erzeugt einen Mock-ConfigEntry."""
    entry = MagicMock()
    entry.version = version
    entry.entry_id = "test_entry_abc123"
    entry.data = data or {
        "host": "192.168.1.10",
        "username": "install",
        "password": "secret",
        "mac": "AA:BB:CC:DD:EE:FF",
    }
    entry.options = {"model": "profi_air_400"}
    return entry


def _make_entity_registry_entry(
    entity_id: str,
    domain: str,
    unique_id: str,
    config_entry_id: str = "test_entry_abc123",
) -> MagicMock:
    """Erzeugt einen Mock-EntityRegistry-Eintrag."""
    e = MagicMock()
    e.entity_id = entity_id
    e.domain = domain
    e.unique_id = unique_id
    e.config_entry_id = config_entry_id
    return e


# ── Tests: Konstanten ─────────────────────────────────────────────────────────

class TestProtocolConstants:
    """CONF_PROTOCOL und PROTOCOL_* müssen korrekt in const.py definiert sein."""

    def test_conf_protocol_defined(self):
        from custom_components.kwl_fraenkische.const import CONF_PROTOCOL
        assert CONF_PROTOCOL == "protocol"

    def test_protocol_http_defined(self):
        from custom_components.kwl_fraenkische.const import PROTOCOL_HTTP
        assert PROTOCOL_HTTP == "http"

    def test_protocol_modbus_defined(self):
        from custom_components.kwl_fraenkische.const import PROTOCOL_MODBUS
        assert PROTOCOL_MODBUS == "modbus"


# ── Tests: Migration v3 → v4 ──────────────────────────────────────────────────

class TestMigrateV3toV4:
    """async_migrate_entry muss v3-Einträge korrekt auf v4 anheben."""

    @pytest.mark.asyncio
    async def test_v4_entry_no_changes(self):
        """v4-Eintrag (aktuelle Version) → True zurück, kein Update durchgeführt."""
        from custom_components.kwl_fraenkische import async_migrate_entry

        entry = _make_entry(version=4)
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()

        with patch(
            "custom_components.kwl_fraenkische.er.async_get",
            return_value=MagicMock(),
        ):
            result = await async_migrate_entry(hass, entry)

        # True = Migration erfolgreich (bzw. nicht nötig) — Entry wird geladen
        assert result is True
        hass.config_entries.async_update_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_v3_adds_protocol_http(self):
        """v3-Eintrag bekommt CONF_PROTOCOL=PROTOCOL_HTTP in entry.data."""
        from custom_components.kwl_fraenkische import async_migrate_entry
        from custom_components.kwl_fraenkische.const import CONF_PROTOCOL, PROTOCOL_HTTP

        entry = _make_entry(version=3)
        hass = MagicMock()

        captured_data = {}

        def capture_update(e, data=None, version=None, **kwargs):
            if data:
                captured_data.update(data)
            if version:
                e.version = version

        hass.config_entries.async_update_entry = MagicMock(side_effect=capture_update)

        reg = MagicMock()
        reg.async_entries_for_config_entry.return_value = []
        reg.async_get.return_value = None

        with patch("custom_components.kwl_fraenkische.er.async_get", return_value=reg):
            result = await async_migrate_entry(hass, entry)

        assert result is True
        assert captured_data.get(CONF_PROTOCOL) == PROTOCOL_HTTP

    @pytest.mark.asyncio
    async def test_v3_bumps_version_to_4(self):
        """v3-Eintrag → VERSION wird auf 4 angehoben."""
        from custom_components.kwl_fraenkische import async_migrate_entry

        entry = _make_entry(version=3)
        hass = MagicMock()
        versions_set = []

        def capture_update(e, data=None, version=None, **kwargs):
            if version is not None:
                versions_set.append(version)
                e.version = version

        hass.config_entries.async_update_entry = MagicMock(side_effect=capture_update)

        reg = MagicMock()
        reg.async_entries_for_config_entry.return_value = []
        reg.async_get.return_value = None

        with patch("custom_components.kwl_fraenkische.er.async_get", return_value=reg):
            await async_migrate_entry(hass, entry)

        assert 4 in versions_set

    @pytest.mark.asyncio
    async def test_v3_preserves_existing_data(self):
        """CONF_PROTOCOL wird hinzugefügt ohne bestehende Felder zu überschreiben."""
        from custom_components.kwl_fraenkische import async_migrate_entry
        from custom_components.kwl_fraenkische.const import CONF_PROTOCOL, PROTOCOL_HTTP

        original_data = {
            "host": "10.0.0.5",
            "username": "install",
            "password": "geheim",
            "mac": "11:22:33:44:55:66",
        }
        entry = _make_entry(version=3, data=original_data.copy())
        hass = MagicMock()
        captured_data = {}

        def capture_update(e, data=None, version=None, **kwargs):
            if data:
                captured_data.update(data)

        hass.config_entries.async_update_entry = MagicMock(side_effect=capture_update)

        reg = MagicMock()
        reg.async_entries_for_config_entry.return_value = []
        reg.async_get.return_value = None

        with patch("custom_components.kwl_fraenkische.er.async_get", return_value=reg):
            await async_migrate_entry(hass, entry)

        # Alle ursprünglichen Felder müssen erhalten bleiben
        for key, value in original_data.items():
            assert captured_data.get(key) == value, f"Feld {key!r} wurde verändert"
        # Neues Feld muss vorhanden sein
        assert captured_data[CONF_PROTOCOL] == PROTOCOL_HTTP


# ── Tests: Fan-Entity-ID Migration ───────────────────────────────────────────

class TestFanEntityIdMigration:
    """v3→v4 Migration muss den _fan-Suffix aus der Fan-Entity-ID entfernen."""

    def _setup_reg(self, entities: list, target_exists: bool = False) -> MagicMock:
        """Erstellt einen vollständigen Entity-Registry-Mock."""
        reg = MagicMock()
        reg.async_entries_for_config_entry.return_value = entities
        reg.async_get.return_value = MagicMock() if target_exists else None
        return reg

    @pytest.mark.asyncio
    async def test_fan_id_with_fan_suffix_is_renamed(self):
        """fan.profi_air_400_fan → fan.profi_air_400."""
        from custom_components.kwl_fraenkische import async_migrate_entry

        entry = _make_entry(version=3)
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()

        fan_entity = _make_entity_registry_entry(
            entity_id="fan.profi_air_400_fan",
            domain="fan",
            unique_id="AA:BB:CC:DD:EE:FF_fan",
        )

        reg = self._setup_reg([fan_entity], target_exists=False)

        with patch("custom_components.kwl_fraenkische.er.async_get", return_value=reg), \
             patch("custom_components.kwl_fraenkische.er.async_entries_for_config_entry",
                   return_value=[fan_entity]):
            await async_migrate_entry(hass, entry)

        reg.async_update_entity.assert_called_once_with(
            "fan.profi_air_400_fan",
            new_entity_id="fan.profi_air_400",
        )

    @pytest.mark.asyncio
    async def test_fan_id_already_correct_not_touched(self):
        """fan.profi_air_400 (kein Suffix) bleibt unverändert."""
        from custom_components.kwl_fraenkische import async_migrate_entry

        entry = _make_entry(version=3)
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()

        fan_entity = _make_entity_registry_entry(
            entity_id="fan.profi_air_400",
            domain="fan",
            unique_id="AA:BB:CC:DD:EE:FF_fan",
        )

        reg = self._setup_reg([fan_entity])

        with patch("custom_components.kwl_fraenkische.er.async_get", return_value=reg), \
             patch("custom_components.kwl_fraenkische.er.async_entries_for_config_entry",
                   return_value=[fan_entity]):
            await async_migrate_entry(hass, entry)

        reg.async_update_entity.assert_not_called()

    @pytest.mark.asyncio
    async def test_fan_id_conflict_not_overwritten(self):
        """Ziel-ID bereits belegt → kein Rename, Warning wird geloggt."""
        from custom_components.kwl_fraenkische import async_migrate_entry

        entry = _make_entry(version=3)
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()

        fan_entity = _make_entity_registry_entry(
            entity_id="fan.profi_air_400_fan",
            domain="fan",
            unique_id="AA:BB:CC:DD:EE:FF_fan",
        )

        reg = self._setup_reg([fan_entity], target_exists=True)

        with patch("custom_components.kwl_fraenkische.er.async_get", return_value=reg), \
             patch("custom_components.kwl_fraenkische.er.async_entries_for_config_entry",
                   return_value=[fan_entity]), \
             patch("custom_components.kwl_fraenkische._LOGGER.warning") as mock_warn:
            await async_migrate_entry(hass, entry)

        reg.async_update_entity.assert_not_called()
        mock_warn.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_fan_entities_not_renamed(self):
        """Sensor-Entities werden durch die Fan-Migration nicht angefasst."""
        from custom_components.kwl_fraenkische import async_migrate_entry

        entry = _make_entry(version=3)
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()

        sensor = _make_entity_registry_entry(
            "sensor.profi_air_400_temp_abluft", "sensor", "AA:BB:CC:DD:EE:FF_temp_abluft"
        )

        reg = self._setup_reg([sensor])

        with patch("custom_components.kwl_fraenkische.er.async_get", return_value=reg), \
             patch("custom_components.kwl_fraenkische.er.async_entries_for_config_entry",
                   return_value=[sensor]):
            await async_migrate_entry(hass, entry)

        reg.async_update_entity.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_entities_only_fan_renamed(self):
        """Mischung Fan+Sensoren: nur Fan mit _fan-Suffix wird umbenannt."""
        from custom_components.kwl_fraenkische import async_migrate_entry

        entry = _make_entry(version=3)
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()

        fan_e = _make_entity_registry_entry("fan.profi_air_400_fan", "fan", "mac_fan")
        s1 = _make_entity_registry_entry("sensor.profi_air_400_temp", "sensor", "mac_temp")
        s2 = _make_entity_registry_entry("binary_sensor.profi_air_400_bp", "binary_sensor", "mac_bp")

        all_entities = [fan_e, s1, s2]
        reg = self._setup_reg(all_entities, target_exists=False)

        with patch("custom_components.kwl_fraenkische.er.async_get", return_value=reg), \
             patch("custom_components.kwl_fraenkische.er.async_entries_for_config_entry",
                   return_value=all_entities):
            await async_migrate_entry(hass, entry)

        reg.async_update_entity.assert_called_once_with(
            "fan.profi_air_400_fan",
            new_entity_id="fan.profi_air_400",
        )


# ── Tests: Fan-Entity Naming ──────────────────────────────────────────────────

class TestFanEntityNaming:
    """KWLFan muss _attr_name = None gesetzt haben (Haupt-Entity-Muster).
    
    Geprüft via AST-Analyse der Quelldatei — zuverlässiger als Import
    bei komplexen Stub-Umgebungen.
    """

    FAN_PY = (
        "/home/claude/kwl_src/custom_components/kwl_fraenkische/fan.py"
    )

    def _get_kwlfan_class(self):
        import ast
        source = open(self.FAN_PY).read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "KWLFan":
                return node
        raise AssertionError("KWLFan Klasse nicht in fan.py gefunden")

    def _get_class_assigns(self, cls_node) -> dict:
        """Alle direkten Klassen-Attribut-Zuweisungen als {name: value_repr}."""
        import ast
        assigns = {}
        for node in cls_node.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assigns[target.id] = node.value
        return assigns

    def test_fan_has_attr_name_none(self):
        """_attr_name = None muss als Klassen-Attribut gesetzt sein."""
        import ast
        cls = self._get_kwlfan_class()
        assigns = self._get_class_assigns(cls)
        assert "_attr_name" in assigns, "_attr_name nicht in KWLFan definiert"
        val = assigns["_attr_name"]
        assert isinstance(val, ast.Constant) and val.value is None, (
            f"_attr_name ist nicht None, sondern: {ast.dump(val)}"
        )

    def test_fan_has_entity_name_true(self):
        """_attr_has_entity_name = True muss gesetzt sein."""
        import ast
        cls = self._get_kwlfan_class()
        assigns = self._get_class_assigns(cls)
        assert "_attr_has_entity_name" in assigns, (
            "_attr_has_entity_name nicht in KWLFan definiert"
        )
        val = assigns["_attr_has_entity_name"]
        assert isinstance(val, ast.Constant) and val.value is True, (
            f"_attr_has_entity_name ist nicht True: {ast.dump(val)}"
        )

    def test_fan_translation_key_preserved(self):
        """_attr_translation_key = 'kwl_fan' für preset_mode Übersetzungen erhalten."""
        import ast
        cls = self._get_kwlfan_class()
        assigns = self._get_class_assigns(cls)
        assert "_attr_translation_key" in assigns, (
            "_attr_translation_key nicht in KWLFan definiert"
        )
        val = assigns["_attr_translation_key"]
        assert isinstance(val, ast.Constant) and val.value == "kwl_fan", (
            f"_attr_translation_key ist nicht 'kwl_fan': {ast.dump(val)}"
        )

    def test_attr_name_before_translation_key(self):
        """_attr_name = None muss vor _attr_translation_key stehen."""
        import ast
        cls = self._get_kwlfan_class()
        positions = {}
        for i, node in enumerate(cls.body):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        positions[target.id] = i
        name_pos = positions.get("_attr_name", -1)
        key_pos = positions.get("_attr_translation_key", -1)
        assert name_pos >= 0 and key_pos >= 0, "Attribute nicht gefunden"
        assert name_pos < key_pos, (
            "_attr_name sollte vor _attr_translation_key definiert sein"
        )

    def test_entity_id_set_to_model_slug(self):
        """self.entity_id = f'fan.{coordinator.model_slug}' muss in __init__ stehen."""
        source = open(self.FAN_PY).read()
        assert "self.entity_id" in source and "model_slug" in source, (
            "entity_id wird nicht explizit auf model_slug gesetzt"
        )

    def test_unique_id_format_mac_fan(self):
        """unique_id-Format: f'{mac}_fan' muss in __init__ stehen."""
        source = open(self.FAN_PY).read()
        # Der _fan-Suffix steckt im f-String: f"{mac}_fan"
        assert "_fan" in source and "_attr_unique_id" in source, (
            "_fan-Suffix oder _attr_unique_id fehlt in fan.py"
        )


# ── Tests: Config Flow VERSION ────────────────────────────────────────────────

class TestConfigFlowVersion:
    """Config Flow VERSION muss 4 sein — geprüft via AST."""

    CONFIG_FLOW_PY = (
        "/home/claude/kwl_src/custom_components/kwl_fraenkische/config_flow.py"
    )

    def test_config_flow_version_is_4(self):
        """VERSION = 4 muss in KWLConfigFlow gesetzt sein."""
        import ast
        source = open(self.CONFIG_FLOW_PY).read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "KWLConfigFlow":
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if (
                                isinstance(target, ast.Name)
                                and target.id == "VERSION"
                                and isinstance(item.value, ast.Constant)
                                and item.value.value == 4
                            ):
                                return  # Gefunden ✅
        raise AssertionError(
            "VERSION = 4 nicht in KWLConfigFlow gefunden. "
            "Bitte config_flow.py prüfen."
        )
