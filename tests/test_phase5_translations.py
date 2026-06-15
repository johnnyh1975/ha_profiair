"""Tests für Phase 5: Translations — alle drei JSON-Dateien vollständig.

Abgedeckte Anforderungen:
- Config-Steps: installer_menu (mit menu_options), confirm_flex (mit Platzhaltern)
- Config-Error: unknown_device_type
- Entity-Sensoren: alle 12 neuen Flex-Sensoren
- Entity-Binary: alarm_active
- Entity-Buttons: filter_reset_flex, alarm_clear
- Entity-Select: operating_mode mit allen 7 Modi-Zuständen
- Entity-Number: filter_total_days_flex
- Alle 3 Dateien: strings.json, de.json, en.json
- JSON-Struktur-Konsistenz zwischen de und en
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

BASE = Path("/home/claude/kwl_src/custom_components/kwl_fraenkische")

FILES = {
    "strings": BASE / "strings.json",
    "de": BASE / "translations/de.json",
    "en": BASE / "translations/en.json",
}

FLEX_MODES = [
    "Manuell", "Bedarfsgesteuert", "Wochenprogramm",
    "Urlaub", "Sommer", "Nacht", "Kaminbetrieb",
]

NEW_SENSOR_KEYS = [
    "current_mode_text", "alarm_text", "preheater_duty_pct",
    "hours_total", "bypass_tmin", "bypass_tmax", "temp_room",
    "voc_ppm", "rh_percent", "co2_ppm",
    "motor_abluft_rpm_flex", "motor_zuluft_rpm_flex",
]


def _load(name: str) -> dict:
    return json.loads(FILES[name].read_text())


@pytest.fixture(params=["strings", "de", "en"])
def translation(request):
    return request.param, _load(request.param)


# ── JSON-Validität ────────────────────────────────────────────────────────────

class TestJsonValid:
    def test_strings_valid_json(self):
        _load("strings")

    def test_de_valid_json(self):
        _load("de")

    def test_en_valid_json(self):
        _load("en")


# ── Config Steps ──────────────────────────────────────────────────────────────

class TestConfigSteps:

    def test_installer_menu_step_in_all_files(self, translation):
        _, data = translation
        assert "installer_menu" in data["config"]["step"]

    def test_installer_menu_has_title(self, translation):
        _, data = translation
        step = data["config"]["step"]["installer_menu"]
        assert "title" in step and step["title"]

    def test_installer_menu_has_menu_options(self, translation):
        _, data = translation
        step = data["config"]["step"]["installer_menu"]
        assert "menu_options" in step

    def test_installer_menu_auth_option(self, translation):
        _, data = translation
        options = data["config"]["step"]["installer_menu"]["menu_options"]
        assert "auth" in options and options["auth"]

    def test_installer_menu_skip_option(self, translation):
        _, data = translation
        options = data["config"]["step"]["installer_menu"]["menu_options"]
        assert "skip_installer" in options and options["skip_installer"]

    def test_confirm_flex_step_in_all_files(self, translation):
        _, data = translation
        assert "confirm_flex" in data["config"]["step"]

    def test_confirm_flex_has_title(self, translation):
        _, data = translation
        step = data["config"]["step"]["confirm_flex"]
        assert "title" in step and step["title"]

    def test_confirm_flex_description_has_model_placeholder(self, translation):
        _, data = translation
        desc = data["config"]["step"]["confirm_flex"]["description"]
        assert "{model}" in desc

    def test_confirm_flex_description_has_firmware_placeholder(self, translation):
        _, data = translation
        desc = data["config"]["step"]["confirm_flex"]["description"]
        assert "{firmware}" in desc

    def test_confirm_flex_description_has_switch_placeholder(self, translation):
        _, data = translation
        desc = data["config"]["step"]["confirm_flex"]["description"]
        assert "{switch}" in desc


# ── Config Errors ─────────────────────────────────────────────────────────────

class TestConfigErrors:

    def test_unknown_device_type_error_in_all_files(self, translation):
        _, data = translation
        assert "unknown_device_type" in data["config"]["error"]

    def test_unknown_device_type_has_type_code_placeholder(self, translation):
        _, data = translation
        msg = data["config"]["error"]["unknown_device_type"]
        assert "{type_code}" in msg


# ── Neue Flex-Sensoren ────────────────────────────────────────────────────────

class TestNewSensorTranslations:

    @pytest.mark.parametrize("key", NEW_SENSOR_KEYS)
    def test_sensor_key_in_all_files(self, key, translation):
        _, data = translation
        assert key in data["entity"]["sensor"], (
            f"Sensor '{key}' fehlt in {translation[0]}"
        )

    @pytest.mark.parametrize("key", NEW_SENSOR_KEYS)
    def test_sensor_has_nonempty_name(self, key, translation):
        _, data = translation
        name = data["entity"]["sensor"].get(key, {}).get("name", "")
        assert name, f"Sensor '{key}' hat keinen Namen in {translation[0]}"


# ── Binary Sensor ─────────────────────────────────────────────────────────────

class TestBinarySensorTranslations:

    def test_alarm_active_in_all_files(self, translation):
        _, data = translation
        assert "alarm_active" in data["entity"]["binary_sensor"]

    def test_alarm_active_has_name(self, translation):
        _, data = translation
        name = data["entity"]["binary_sensor"]["alarm_active"].get("name", "")
        assert name


# ── Buttons ──────────────────────────────────────────────────────────────────

class TestButtonTranslations:

    def test_filter_reset_flex_in_all_files(self, translation):
        _, data = translation
        assert "filter_reset_flex" in data["entity"]["button"]

    def test_alarm_clear_in_all_files(self, translation):
        _, data = translation
        assert "alarm_clear" in data["entity"]["button"]

    def test_filter_reset_flex_has_name(self, translation):
        _, data = translation
        name = data["entity"]["button"]["filter_reset_flex"].get("name", "")
        assert name

    def test_alarm_clear_has_name(self, translation):
        _, data = translation
        name = data["entity"]["button"]["alarm_clear"].get("name", "")
        assert name


# ── Select ────────────────────────────────────────────────────────────────────

class TestSelectTranslations:

    def test_operating_mode_in_all_files(self, translation):
        _, data = translation
        assert "operating_mode" in data["entity"]["select"]

    def test_operating_mode_has_state_section(self, translation):
        _, data = translation
        sel = data["entity"]["select"]["operating_mode"]
        assert "state" in sel

    def test_operating_mode_all_7_states_present(self, translation):
        name, data = translation
        states = data["entity"]["select"]["operating_mode"]["state"]
        # Keys sind die deutschen Modi-Namen (device-seitig)
        for mode in FLEX_MODES:
            assert mode in states, (
                f"Modus '{mode}' fehlt in operating_mode.state in {name}"
            )

    def test_operating_mode_state_values_nonempty(self, translation):
        name, data = translation
        states = data["entity"]["select"]["operating_mode"]["state"]
        for mode, label in states.items():
            assert label, f"Leeres Label für Modus '{mode}' in {name}"


# ── Number ────────────────────────────────────────────────────────────────────

class TestNumberTranslations:

    def test_filter_total_days_flex_in_all_files(self, translation):
        _, data = translation
        assert "filter_total_days_flex" in data["entity"]["number"]

    def test_filter_total_days_flex_has_name(self, translation):
        _, data = translation
        name = data["entity"]["number"]["filter_total_days_flex"].get("name", "")
        assert name


# ── Konsistenz-Prüfung: DE vs EN ─────────────────────────────────────────────

class TestDeEnConsistency:
    """Beide Sprachen müssen dieselben Keys haben."""

    def test_config_steps_same_keys(self):
        de_steps = set(_load("de")["config"]["step"].keys())
        en_steps = set(_load("en")["config"]["step"].keys())
        assert de_steps == en_steps, (
            f"Steps nur in DE: {de_steps - en_steps}\n"
            f"Steps nur in EN: {en_steps - de_steps}"
        )

    def test_config_errors_same_keys(self):
        de = set(_load("de")["config"]["error"].keys())
        en = set(_load("en")["config"]["error"].keys())
        assert de == en

    def test_sensor_keys_same(self):
        de = set(_load("de")["entity"]["sensor"].keys())
        en = set(_load("en")["entity"]["sensor"].keys())
        assert de == en

    def test_binary_sensor_keys_same(self):
        de = set(_load("de")["entity"]["binary_sensor"].keys())
        en = set(_load("en")["entity"]["binary_sensor"].keys())
        assert de == en

    def test_button_keys_same(self):
        de = set(_load("de")["entity"]["button"].keys())
        en = set(_load("en")["entity"]["button"].keys())
        assert de == en

    def test_select_keys_same(self):
        de = set(_load("de")["entity"]["select"].keys())
        en = set(_load("en")["entity"]["select"].keys())
        assert de == en

    def test_number_keys_same(self):
        de = set(_load("de")["entity"]["number"].keys())
        en = set(_load("en")["entity"]["number"].keys())
        assert de == en

    def test_operating_mode_state_keys_same(self):
        de = set(_load("de")["entity"]["select"]["operating_mode"]["state"].keys())
        en = set(_load("en")["entity"]["select"]["operating_mode"]["state"].keys())
        assert de == en, (
            f"State-Keys nur in DE: {de - en}\n"
            f"State-Keys nur in EN: {en - de}"
        )
