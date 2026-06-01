# Changelog

All notable changes to this project will be documented in this file.

---

## [1.3.0] - 2026-05-31

This release consolidates all work since v1.2.0 into a single coherent release.
The version jump from 1.2 reflects genuine feature additions; intermediate patch
versions (1.3–1.5) have been collapsed here as they were primarily bugfixes
that should never have been separate minor versions.

### Added

**New entities**
- `binary_sensor.kwl_frost_risiko` — frost risk for heat exchanger (Außenluft < -5°C and Zuluft < 5°C)
- `binary_sensor.kwl_bypass_leckage` — bypass leakage detected from temperature delta (disabled by default)
- `binary_sensor.kwl_motor_asymmetrie` — motor RPM asymmetry > 15%, sign of wear (disabled by default)
- `binary_sensor.kwl_bypass_vorkuehlung_empfohlen` — bypass pre-cooling currently beneficial
- `binary_sensor.kwl_digital_input_1/2/3` — physical digital inputs (disabled by default)
- `sensor.kwl_waermerueckgewinnungsgrad` — heat recovery efficiency η in %, with force_update
- `sensor.kwl_rueckgewonnene_waermeleistung` — recovered heat output in W

**Repair Issues**
- `filter_needs_replacement` — already present, now also deleted when resolved
- `annual_maintenance_due` — fires after 8760 operating hours, fixable, deleted after confirmation
- `bypass_leaking` — fires after 3 consecutive positive polls (prevents false alarms)
- `motor_asymmetry` — fires after 3 consecutive positive polls

**Configuration**
- Options Flow — poll interval (30–300 s) and watt values adjustable after setup without reinstalling
- `async_migrate_entry` — automatically migrates v1 Config Entries to v2 (adds missing watt values)
- `CONFIG_FLOW VERSION = 2`

**Code quality**
- `entity_category` CONFIG/DIAGNOSTIC on all relevant entities
- Complete EN + DE translations — all entities, options, repair issues
- Minimum XML tag validation — `UpdateFailed` on partial response
- `KWLWattSensor` subclass — clean separation of watt_map-dependent sensors
- 218 automated tests (up from 161 in v1.2.0)

### Fixed

**Bugs that would have caused runtime errors**
- Setup order in `__init__.py`: `runtime_data` now set before `async_setup()` — previously could cause `AttributeError` if time sync timer fired before runtime_data was available
- `button.py`: `await _get_session()` → `_get_session()` — would have raised `TypeError` on every button press
- `button.py`: `RuntimeError` → `HomeAssistantError`
- `fan.py`: `data.control_mode` → `data.program_control` — would have raised `AttributeError` on every dashboard refresh
- All 7 derived binary sensors were never added to the `BINARY_SENSORS` tuple — they simply did not exist in HA despite being in translations and coordinator

**Correctness**
- `reconfigure_flow`: now uses `{**entry.data, ...}` — previously overwrote watt values on IP/auth change
- `annual_maintenance_due` Repair Issue: now deleted when hours drop below threshold and after confirmation
- `bypass_leaking`/`motor_asymmetry` Repair Issues: 3-poll threshold prevents false alarms on measurement spikes
- `repairs.py`: `self.issue_data` → `self.data` (correct RepairsFlow attribute)
- `entity_category` type: `str | None` → `EntityCategory | None` in all dataclasses
- Exhaust airflow entities: correct `required_tag` per sensor (e.g. `st1a` not `st1z`)
- Dead Translation keys `language`/`program_control` in select removed
- Broken "adaptive polling" removed — `update_interval` was set and immediately reset with no effect

**Code hygiene**
- `async_close_session`: dead code removed
- `DOMAIN`: unused import in `binary_sensor.py` removed
- `safety_active`, `passive_mode`, `preheater_active`: `entity_category=DIAGNOSTIC` added
- `_is_supported`: `getattr` replaced with direct Protocol access
- `unknown_tags`: logged only once after Discovery, not on every poll
- Heat recovery η guard reduced from 3.0 K to 1.5 K (summer measurements were returning None)
- `SCAN_INTERVAL` dead constant removed from coordinator
- Docstring-after-code in `_async_sync_time` fixed
- Duplicate `control_mode`/`program_control` property removed
- Dead comment blocks from removed features cleaned up
- `"Außenluft"` umlaut corrected in number.py
- `"Nennlueftung"`/`"Intensivlueftung"` corrected (was double-e)
- `_LOGGER` added to `__init__.py`

---

## [1.2.0] - 2026-05-22

### Added
- Digital inputs DiIn1/2/3 as binary sensors (disabled by default)
- All firmware v2 tags (prg1–prg10, soze, time, date, events, langtxt0–154 etc.)
  added to ALL_KNOWN_TAGS — zero unknown tag warnings after firmware update

---

## [1.1.0] - 2026-05-21

### Added
- **Capability Discovery** — automatically detects what your firmware supports on first startup
- No unavailable entities for features the firmware does not expose
- Unknown XML tags logged with direct GitHub issue link
- `required_tag` / `required_endpoint` per EntityDescription
- Two firmware fixtures in tests (full / minimal)
- Profi-Air 250 Touch / 400 Touch explicitly supported and documented

---

## [1.0.0] - 2026-05-20

### Added
- Initial release
- Fan entity with levels 1–4, percentage slider and preset modes
- Bypass control (Manual open / Manual closed / Automatic)
- All four temperatures: exhaust, supply, outdoor, extract air
- Motor RPM and voltage sensors
- Current power (W) and cumulative energy per level (kWh) — Energy Dashboard ready
- Filter status binary sensor + Repair Issue with one-click fix
- Party timer, bypass thresholds, temperature corrections as number entities
- House type, pre-heater, safety manager, external sensor types as select entities
- Installer settings via HTTP Basic Auth (`/install/install.htm`)
- Automatic time synchronisation incl. DST on startup and every 24 h
- Optimistic updates — UI responds immediately without waiting for next poll
- Re-auth flow, Reconfigure flow
- Full translations DE + EN
- Download diagnostics with auto-redacting
- 161 automated tests
- Quality Scale: Platinum
