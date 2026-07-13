"""Guard: alle State-Übersetzungsschlüssel müssen Slugs sein (hassfest-Regel).

Home Assistant verlangt für Übersetzungsschlüssel unterhalb von `state`:
    [a-z0-9-_]+, nicht mit Bindestrich/Unterstrich beginnend oder endend

Bis 2.0.x verwendete diese Integration deutschen Klartext als Entity-State
("Manuell offen", "Stufe 4 - Intensivlueftung"). hassfest lehnte das ab
([TRANSLATIONS] Invalid translation key). Mit 2.1.0 sind alle States Slugs;
die Anzeigenamen stehen als WERTE in den Übersetzungen.

Dieser Test bildet die hassfest-Regel nach, damit ein Rückfall sofort in der
lokalen Suite auffällt und nicht erst im CI-Container.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_CC = Path(__file__).resolve().parent.parent / "custom_components" / "kwl_fraenkische"

TRANSLATION_FILES = [
    _CC / "strings.json",
    _CC / "translations" / "de.json",
    _CC / "translations" / "en.json",
]

# Exakt die hassfest-Regel
SLUG_RE = re.compile(r"^[a-z0-9]([a-z0-9_-]*[a-z0-9])?$")


def _collect_state_keys(node, path: str, found: list[tuple[str, str]]) -> None:
    """Sammelt rekursiv alle Schlüssel unterhalb eines `state`-Dicts."""
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        if key == "state" and isinstance(value, dict):
            for state_key in value:
                found.append((f"{path}.state", state_key))
        _collect_state_keys(value, f"{path}.{key}", found)


@pytest.mark.parametrize("path", TRANSLATION_FILES, ids=lambda p: p.name)
def test_all_state_keys_are_slugs(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    found: list[tuple[str, str]] = []
    _collect_state_keys(data.get("entity", {}), "entity", found)

    assert found, f"{path.name}: keine state-Schlüssel gefunden – Test wäre wirkungslos"

    invalid = [(loc, k) for loc, k in found if not SLUG_RE.match(k)]
    assert not invalid, (
        f"{path.name} enthält State-Schlüssel, die keine Slugs sind – "
        f"hassfest lehnt das ab:\n"
        + "\n".join(f"    {loc} -> {k!r}" for loc, k in invalid)
    )


class TestSlugMigration2_1_0:
    """Die konkreten Slugs, auf die 2.1.0 umgestellt hat.

    Festgeschrieben, weil eine spätere Umbenennung ein ZWEITER Breaking Change
    für Nutzer-Automationen wäre – das soll niemand versehentlich tun.
    """

    def test_fan_preset_slugs(self):
        import sys
        sys.path.insert(0, str(_CC.parent))
        from kwl_fraenkische.fan import PRESET_MODES

        assert list(PRESET_MODES) == ["level_1", "level_2", "level_3", "level_4"]
        assert PRESET_MODES["level_4"] == 4

    def test_bypass_slugs(self):
        import sys
        sys.path.insert(0, str(_CC.parent))
        from kwl_fraenkische.select import BYPASS_OPTIONS

        assert set(BYPASS_OPTIONS) == {"manual_open", "manual_closed", "automatic"}
        # Die Geräte-Payloads dürfen sich NICHT geändert haben
        assert BYPASS_OPTIONS["manual_open"] == "bypa0"
        assert BYPASS_OPTIONS["manual_closed"] == "bypa1"
        assert BYPASS_OPTIONS["automatic"] == "bypa2"

    def test_device_status_texts_unchanged(self):
        """Die Geräte-Statustexte (Input) bleiben deutsch – nur die HA-Option
        (Output) ist ein Slug. Ein Vertauschen würde die Bypass-Erkennung
        stillschweigend kaputtmachen."""
        import sys
        sys.path.insert(0, str(_CC.parent))
        from kwl_fraenkische.select import BYPASS_STATUS_MAP, _parse_bypass

        assert "man.: offen" in BYPASS_STATUS_MAP  # Geräte-Text, deutsch
        assert _parse_bypass("Man.: Offen") == "manual_open"  # -> Slug
        assert _parse_bypass("Auto: Zu") == "automatic"

    def test_repair_issue_exists(self):
        """Das Migrations-Repair-Issue trägt bei 2.1.0 die Warnlast (die
        Versionsnummer signalisiert den Breaking Change nicht)."""
        for path in TRANSLATION_FILES:
            data = json.loads(path.read_text(encoding="utf-8"))
            issues = data.get("issues", {})
            assert "slug_states_2_1_0" in issues, (
                f"{path.name}: Repair-Issue 'slug_states_2_1_0' fehlt"
            )
            issue = issues["slug_states_2_1_0"]
            assert issue.get("title") and issue.get("description")
            # Die Mapping-Tabelle muss drin stehen, sonst nützt der Hinweis nichts
            assert "level_4" in issue["description"]
            assert "manual_open" in issue["description"]
