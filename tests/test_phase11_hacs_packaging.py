"""Guard tests für den HACS zip_release-Packaging-Vertrag.

Mit `zip_release` entpackt HACS das Release-Asset OHNE Pfad-Stripping direkt
nach custom_components/kwl_fraenkische/. Drei Invarianten müssen daher gelten,
sonst bricht jede Installation und jedes Update:

  1. hacs.json setzt zip_release + filename
  2. der filename in hacs.json ist EXAKT der Asset-Name, den release.yml baut
     (und trägt keine Version -- HACS sucht in jedem Release nach dem
     literalen Namen)
  3. es liegt keine hacs.json innerhalb des Integrations-Ordners -- sie würde
     sonst mit ins ZIP gepackt, was HACS verbietet

Diese Tests existieren, weil genau dieser Fehler (doppelte Verschachtelung
custom_components/<domain>/custom_components/<domain>/...) eine bekannte,
in der Praxis schon aufgetretene Falle der zip_release-Konvention ist.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HACS_JSON = ROOT / "hacs.json"
INTEGRATION_DIR = ROOT / "custom_components" / "kwl_fraenkische"
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"

EXPECTED_ASSET = "ha-profiair.zip"


class TestHacsZipReleaseContract:
    def test_hacs_json_enables_zip_release(self):
        d = json.loads(HACS_JSON.read_text(encoding="utf-8"))
        assert d.get("zip_release") is True, "hacs.json muss zip_release: true setzen"
        assert d.get("filename"), "hacs.json muss einen filename setzen"

    def test_filename_matches_release_asset(self):
        """Der in hacs.json genannte Asset-Name muss exakt der sein, den
        release.yml baut und anhängt. Weicht er ab, findet HACS das Asset
        nicht und Installation/Update schlagen fehl."""
        d = json.loads(HACS_JSON.read_text(encoding="utf-8"))
        assert d["filename"] == EXPECTED_ASSET

        wf = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        # Das ZIP wird unter genau diesem Namen gebaut ...
        assert f'zip -r "${{GITHUB_WORKSPACE}}/{EXPECTED_ASSET}"' in wf, (
            f"release.yml baut kein {EXPECTED_ASSET}"
        )
        # ... und als Release-Asset angehängt.
        assert EXPECTED_ASSET in wf.split("files:")[-1], (
            f"{EXPECTED_ASSET} fehlt in der files:-Liste des Releases"
        )

    def test_asset_name_carries_no_version(self):
        """HACS sucht nach dem literalen filename aus hacs.json. Ein
        versionierter Name (ha-profiair-v2.0.8.zip) würde in keinem Release
        gefunden werden."""
        d = json.loads(HACS_JSON.read_text(encoding="utf-8"))
        name = d["filename"]
        assert "$" not in name and "{" not in name
        # keine Ziffernfolge, die wie eine Version aussieht
        assert not any(part.replace(".", "").isdigit() for part in name.split("-"))

    def test_no_hacs_json_inside_integration(self):
        """Eine hacs.json im Integrations-Ordner landet mit im ZIP -- HACS
        verbietet das (es liest hacs.json ausschliesslich aus dem Repo-Root
        via GitHub-API)."""
        inner = INTEGRATION_DIR / "hacs.json"
        assert not inner.exists(), (
            "custom_components/kwl_fraenkische/hacs.json darf nicht existieren: "
            "sie würde ins HACS-ZIP gepackt. hacs.json gehört nur ins Repo-Root."
        )

    def test_manifest_is_at_integration_root(self):
        """manifest.json muss direkt im Integrations-Ordner liegen -- daraus
        wird es beim zip_release-Build zur ZIP-Wurzel."""
        assert (INTEGRATION_DIR / "manifest.json").exists()

    def test_release_workflow_validates_zip_structure(self):
        """Der Packaging-Schritt muss maschinell abgesichert sein, nicht nur
        kommentiert."""
        wf = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        assert "Validate HACS ZIP structure" in wf
        # die drei Regeln müssen geprüft werden
        assert 'grep -qx "manifest.json"' in wf
        assert 'grep -q "custom_components"' in wf
        assert 'grep -qx "hacs.json"' in wf


class TestHacsJsonSchema:
    """hacs.json darf nur HACS-eigene Keys enthalten.

    Realer CI-Fehler: hacs.json trug ein `iot_class: local_polling`. Das ist
    ein manifest.json-Key -- HACS lehnt ihn mit "extra keys not allowed" ab.
    Er stand ohnehin (korrekt) im manifest.json, war in hacs.json also eine
    Dublette am falschen Ort.
    """

    # Von HACS erlaubte Keys (https://hacs.xyz/docs/publish/include)
    ALLOWED = {
        "name", "content_in_root", "country", "filename", "hacs",
        "hide_default_branch", "homeassistant", "persistent_directory",
        "render_readme", "zip_release",
    }

    def test_only_allowed_keys(self):
        d = json.loads(HACS_JSON.read_text(encoding="utf-8"))
        extra = set(d) - self.ALLOWED
        assert not extra, (
            f"hacs.json enthält Keys, die HACS nicht erlaubt: {sorted(extra)}. "
            f"Erlaubt sind nur: {sorted(self.ALLOWED)}"
        )

    def test_iot_class_lives_in_manifest_not_hacs_json(self):
        """iot_class gehört ins manifest.json, nicht in hacs.json."""
        hacs = json.loads(HACS_JSON.read_text(encoding="utf-8"))
        assert "iot_class" not in hacs

        manifest = json.loads(
            (INTEGRATION_DIR / "manifest.json").read_text(encoding="utf-8")
        )
        assert manifest.get("iot_class"), "iot_class fehlt im manifest.json"

    def test_manifest_has_no_disallowed_icon_key(self):
        """Realer hassfest-Fehler: `icon` ist im manifest.json nicht erlaubt
        (Integrations-Icons gehören nach icons.json bzw. ins brands-Repo)."""
        manifest = json.loads(
            (INTEGRATION_DIR / "manifest.json").read_text(encoding="utf-8")
        )
        assert "icon" not in manifest, (
            "manifest.json darf keinen 'icon'-Key haben -- hassfest lehnt das ab"
        )
