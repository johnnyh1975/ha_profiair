# KWL Fränkische Rohrwerke — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2026.3%2B-blue.svg)](https://www.home-assistant.io/)
[![Tests](https://img.shields.io/badge/Tests-219%20passing-brightgreen.svg)](.github/workflows/validate.yaml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-1.4.0-blue.svg)](CHANGELOG.md)

> **What this integration makes possible:** a profi-air 250 or 400 touch that learns your home, optimises summer night cooling automatically, detects maintenance needs before they become faults, and tracks its own energy efficiency — without any cloud service, without a new device, and without changing the device firmware.

---

## Table of Contents

- [What you get](#what-you-get)
- [Supported devices](#supported-devices)
- [Requirements](#requirements)
- [Installation](#installation)
- [First-time setup](#first-time-setup)
- [Day one — immediate features](#day-one--immediate-features)
- [Week one — baselines establish](#week-one--baselines-establish)
- [First winter — full diagnostics activate](#first-winter--full-diagnostics-activate)
- [Summer night cooling automation](#summer-night-cooling-automation)
- [All entities](#all-entities)
- [Options and calibration](#options-and-calibration)
- [After filter replacement](#after-filter-replacement)
- [Firmware bypass settings](#firmware-bypass-settings)
- [Energy dashboard](#energy-dashboard)
- [Troubleshooting](#troubleshooting)
- [Known firmware behaviour](#known-firmware-behaviour)
- [Changelog](#changelog)

---

## What you get

The profi-air 250 and 400 touch are excellent ventilation units with a built-in weekly schedule and a local HTTP interface. What they lack is any awareness of the outside world — weather, indoor temperature trends, season changes, or their own performance over time.

This integration adds that intelligence layer entirely within Home Assistant:

| | Without this integration | With this integration |
|---|---|---|
| **Control** | Device touchscreen + weekly schedule | HA dashboard + automations |
| **Summer cooling** | Manual bypass toggle | Automatic night pre-cooling based on weather + indoor temperature |
| **Maintenance alerts** | "F1" on display when filter is overdue | Early warning days before, plus bypass hunting, motor anomaly, efficiency baseline |
| **Energy tracking** | None | Cumulative kWh per level in HA Energy Dashboard |
| **Efficiency** | No feedback | Real-time heat recovery efficiency with self-calibrating seasonal baseline |
| **Power monitoring** | None | Continuous watt estimate from motor RPM — EC motor model P = P_base + k × (RPM/RPM_ref)³ |
| **Self-learning** | None | Analytics engine builds device-specific baselines over first weeks and months |

Everything runs locally. No cloud, no subscription, no external services.

---

## Supported devices

| Device | Status |
|---|---|
| **profi-air 400 touch** | ✅ Full support |
| **profi-air 250 touch** | ✅ Full support |
| profi-air with external sensors (Artikelnr. 78300831/78300832) | ✅ External sensor entities included |
| Older profi-air models (classic firmware) | ✅ Core entities via capability discovery |

The integration automatically detects your firmware capabilities on first start. Entities that your device does not support are simply not created.

---

## Requirements

- Home Assistant 2026.3 or newer
- [HACS](https://hacs.xyz) installed
- profi-air device reachable on your local network at a static IP
- Installer credentials (factory default: `install` / `konfig12` — change this if you have not)

---

## Installation

**Via HACS (recommended)**

1. HACS → Integrations → menu (⋮) → Custom repositories
2. Add `https://github.com/johnnyh1975/ha-kwl-fraenkische` — category Integration
3. Search for **KWL Fränkische Rohrwerke**, install, restart HA

**Manual**

Copy `custom_components/kwl_fraenkische` into your `config/custom_components/` directory, then restart HA.

---

## First-time setup

Go to **Settings → Devices & Services → Add Integration**, search for **KWL Fränkische Rohrwerke**.

**Step 1 — IP address**
Enter the local IP of your KWL (e.g. `10.10.4.1`). The integration checks connectivity immediately.

**Step 2 — Installer credentials**
Enter the username and password for the installer area. Factory defaults: `install` / `konfig12`.
Change this password on the device if you have not already done so.

**Step 3 — Power reference values**
These determine the accuracy of the Energy Dashboard and anchor the real-time power calculation. The 400 touch defaults are **measured values** (clamp meter, four levels). The 250 touch defaults are estimates — measure your own installation for accuracy.

| | profi-air 250 touch | profi-air 400 touch |
|---|---|---|
| Stufe 1 – Feuchteschutz | 4 W | **11 W** |
| Stufe 2 – Reduziert | 8 W | **17.5 W** |
| Stufe 3 – Nennlüftung | 23 W | **43.5 W** |
| Stufe 4 – Intensivlüftung | 45 W | **80 W** |

All four values are individually configurable. Stufe 4 is the primary anchor — the integration derives real-time power at all other speeds from it using the EC motor model (see below).

**After setup — set your device model**
Settings → Devices & Services → KWL → Configure → select your model. This activates model-appropriate defaults and enables model-specific airflow estimation.

---

## Day one — immediate features

These work from the first poll, no learning required.

### Live sensor data

Every value from `status.xml` is exposed: all four air temperatures, motor RPM and voltage for both fans, bypass state, current fan level, filter remaining days, party timer, and operating hours per level.

### Real-time power from motor RPM — EC motor model

`power_current` is computed continuously from the actual motor RPM using a two-parameter EC motor model:

```
P = P_base + k × (RPM / RPM_ref)³
```

`P_base` (~9 W) is the fixed overhead of the EC motor's control electronics and minimum field excitation — present at any fan speed. `k` is the aerodynamic component that follows the cubic fan law. Both parameters are derived automatically via least-squares from your four configured watt values and the measured RPM ratios.

For the 400 touch with measured values 11 / 17.5 / 43.5 / 80 W:
**P = 8.93 + 71.71 × (RPM / 2538)³** — R² = 0.9989, max residual 1.5 W.

This model is significantly more accurate than a pure P ∝ n³ law, which would underestimate Stufe 1 by 72% (giving 3 W instead of the measured 11 W). The base overhead is why EC motors draw disproportionately more power at low speeds than the simple cubic law predicts. The sensor updates every poll and correctly tracks ramp-ups, party mode, and intermediate speeds.

### Heat recovery efficiency

`waermerueckgewinnungsgrad` shows supply-side η in real time, gated to temperature deltas ≥ 3K (below which sensor noise dominates). At 87–88% rated efficiency, summer values of 40–65% are completely normal when the bypass is open — the integration correctly suppresses misleading values in that regime.

`rueckgewonnene_waermeleistung` estimates recovered heat watts using RPM-based airflow (Q ∝ RPM, anchored to the vendor's Bezugs-Volumenstrom).

### Bypass hunting detection

`binary_sensor.bypass_hunting` activates immediately. It watches the bypass for rapid open/closed cycling — more than 5 transitions in 60 minutes, or average open episode duration below 15 minutes. The device firmware has no awareness of actuator cycling frequency; this integration surfaces it.

### Night cooling result tracking

`night_cooling_last_k` and `night_cooling_7d_avg_k` record the actual T_abluft drop (°C/K) per Stufe-4 cooling activation. From day one you can see whether your summer cooling automation is genuinely cooling the building and by how much per session.

### Maintenance alerts (Repair Issues)

Active notifications appear in the HA Repairs panel:
- Filter replacement due (device-reported via `filter0`)
- Annual maintenance due (8760 cumulative operating hours)
- Bypass leakage — heating mode (delta ≥ 5K) and summer mode (2–5K, bypass explicitly closed)
- Motor asymmetry — >22% RPM deviation or reversed direction (exhaust faster than supply)

---

## Week one — baselines establish

The `analytics_maturity` sensor shows 0–100% readiness. After approximately 4–8 hours of operation at each fan level, summer RPM baselines reach their minimum sample count (500 readings). Once established, these analytics become active:

**`rpm_anomaly`** — fires when abluft RPM drops more than 3 standard deviations below the established baseline for the current level and season. Detects motor bearing wear. Unlike the hard-threshold asymmetry check, this alert is calibrated to your specific device's normal behaviour and adjusted for seasonal air density variation.

**`ratio_anomaly`** — fires when the Zuluft/Abluft RPM ratio deviates from its baseline by more than 3σ. Your device structurally runs supply ~20% faster than exhaust. A shift indicates asymmetric degradation on one side.

**`fan_law_max_deviation`** — maximum residual between your configured watt values and the two-parameter EC motor model prediction at the same RPMs, expressed as a percentage of P_Stufe4. For the 400 touch with measured values this reads ~1.9% (1.5 W max residual). Values above 5% trigger `fan_law_anomaly` and indicate either a measurement inconsistency or a motor anomaly. Note: a pure P ∝ n³ check would show 256% deviation at Stufe 1 on a perfectly healthy motor — that is why this integration uses the EC motor model instead.

**`spi_stufe4`** — Specific Power Input at Stufe 4 in W/(m³/h). Record this value when you first set up. An increase of 15% or more on a re-measurement after months of operation is a direct signal that the motor draws more power for the same airflow — bearing wear or increased system resistance.

---

## First winter — full diagnostics activate

These require the bypass to be closed, a minimum indoor-outdoor delta of 5–8K, and sufficient gated readings accumulated during the heating season.

**`hre_abluftseite`** (ε_exhaust) — exhaust-side heat recovery efficiency. Measures how much heat the HRE extracted from the exhaust stream. Independent of the supply-side η, it characterises the exhaust half of the heat exchanger separately. Vendor rated: 87–88%.

**`energy_balance_ratio`** — ratio of (T_abluft − T_fortluft) to (T_zuluft − T_aussenluft). In balanced flow this equals the Zuluft/Abluft RPM ratio (~1.20 for a typical installation). Deviation indicates sensor drift or asymmetric HRE fouling, and reveals which side is affected.

**`wrg_unter_referenzwert`** — fires when η drops 8 percentage points below its established seasonal mean. In winter, a sustained drop below ~75% on a clean device indicates filter restriction or HRE fouling.

---

## Summer night cooling automation

The integration ships with a validated two-part automation pair for automatic summer night pre-cooling.

### What it does
- Activates Stufe 4 between 22:00 and 07:00 when outdoor air is cooler than indoor by at least 3K (configurable)
- Guards on dew point — prevents humid summer nights from increasing indoor humidity
- Gates on `binary_sensor.kwl_sommertag`: either tomorrow's DWD forecast ≥ 25°C **or** indoor temperature already ≥ 24°C (captures warm-building nights independent of forecast)
- Resets to Stufe 1 or 2 at sunrise/07:00 based on presence
- Corrects firmware fan-level resets during the day without waiting for 22:00

### Prerequisites

Create two binary sensor helpers (Settings → Helpers → Template → Binary sensor):

**`kwl_sommer_kuehlung_aktiv`**
```
{{ is_state_attr('fan.kwl_fraenkische_rohrwerke', 'preset_mode', 'Stufe 4 - Intensivlueftung') }}
```

**`kwl_sommertag`**
```
{% set schwelle = states('input_number.kwl_bypass_hitze_schwelle') | float(25) %}
{% set morgen   = states('sensor.dwd_tagesmax_temperatur_morgen') | float(0) %}
{% set abluft   = states('sensor.kwl_fraenkische_rohrwerke_abluft_temperatur') | float(0) %}
{{ morgen > schwelle or abluft >= 24 }}
```

Create these `input_number` helpers:

| Helper | Value | Purpose |
|---|---|---|
| `kwl_bypass_delta_schwelle` | 3.0 | Outdoor must be this many K cooler than indoor to activate |
| `kwl_bypass_delta_aus_schwelle` | 1.0 | Close threshold — gives 2K hysteresis |
| `kwl_komfort_min_temperatur` | your preference | Minimum indoor T_abluft for cooling to activate |
| `kwl_bypass_hitze_schwelle` | 25.0 | DWD forecast threshold for Sommertag |

### Firmware bypass settings (required)

Set both bypass Auto thresholds to minimum via the integration's number entities or the device web UI:
- **Bypass Außenluft-Schwelle** → **13°C**
- **Bypass Abluft-Schwelle** → **18°C**

This prevents the device firmware from fighting the HA automation during the night cooling window.

### Automation YAML

Full `kwl_sommer_ein.yaml` and `kwl_sommer_aus.yaml` are in the `automations/` folder of this repository.

---

## All entities

### Sensors — always active

| Key | Description |
|---|---|
| `temp_abluft` | Extract air temperature |
| `temp_zuluft` | Supply air temperature |
| `temp_aussenluft` | Outdoor intake temperature |
| `temp_fortluft` | Exhaust air temperature |
| `motor_zuluft_rpm` | Supply fan RPM |
| `motor_abluft_rpm` | Exhaust fan RPM |
| `motor_zuluft_volt` | Supply motor voltage setpoint |
| `motor_abluft_volt` | Exhaust motor voltage setpoint |
| `bypass_status` | Bypass state string |
| `current_level_text` | Current fan level |
| `party_timer` | Party mode remaining (min) |
| `system_message` | Device status string |
| `heat_recovery_efficiency` | Supply-side η (%) — gated δ ≥ 3K |
| `heat_recovery_watts` | Recovered heat estimate (W) — RPM-based |
| `power_current` | Real-time power from RPM (W) |
| `energy_level_1` through `_4` | Cumulative energy per level (kWh) |
| `hours_level_1` through `_4` | Operating hours per level (h) |
| `hours_frost` | Frost protection hours (h) |
| `filter_total_days` | Filter total interval (days) |
| `filter_residual_days` | Filter remaining days |

### Sensors — analytics (diagnostic, disabled by default)

| Key | Active from | Description |
|---|---|---|
| `analytics_maturity` | Day 1 | Baseline readiness 0–100% |
| `analytics_season` | Day 1 | Current season (summer/winter) |
| `bypass_open_pct` | Day 1 | % time bypass open (cumulative) |
| `bypass_avg_open_min` | Day 1 | Avg open episode duration (min) |
| `bypass_transitions_1h` | Day 1 | Transitions in last 60 min |
| `night_cooling_last_k` | Day 1 | Last cooling activation delta (K) |
| `night_cooling_7d_avg_k` | Day 1 | 7-day average cooling delta (K) |
| `rpm_ratio` | Week 1 | Current Zu/Ab RPM ratio |
| `fan_law_max_deviation` | Week 1 | Max watt vs fan law deviation (%) |
| `spi_stufe4` | Week 1 | Specific Power Input Stufe 4 (W/m³/h) |
| `eps_exhaust` | Winter | Exhaust-side HRE efficiency ε (%) |
| `energy_balance_ratio` | Winter | Four-sensor energy balance ratio |

### Binary sensors — always active

| Key | Fires when |
|---|---|
| `filter_ok` | Filter needs replacement |
| `frost_risk` | T_aussen < −5°C and T_zuluft < 5°C |
| `bypass_leaking` | Fortluft tracks Aussenluft despite bypass closed |
| `motor_asymmetry` | >22% RPM deviation or reversed direction |
| `bypass_recommended` | Outdoor ≥ 3K cooler than indoor, T_ab > 22°C, T_au > 10°C |

### Binary sensors — analytics (diagnostic, disabled by default)

| Key | Active from | Fires when |
|---|---|---|
| `bypass_hunting` | Day 1 | >5 transitions/hour or avg open episode <15 min |
| `rpm_anomaly` | Week 1 | Abluft RPM >3σ below level+season baseline |
| `ratio_anomaly` | Week 1 | Zu/Ab ratio >3σ from baseline |
| `eta_below_baseline` | Winter | η drops ≥8pp below seasonal baseline mean |
| `fan_law_anomaly` | Week 1 | Any level >15% deviation from fan law prediction |

### Controls

| Entity | Description |
|---|---|
| `fan.kwl_fraenkische_rohrwerke` | Fan level 1–4 |
| `select.bypass_steuerung` | Automatisch / Manuell offen / Manuell zu |
| `number.bypass_schwelle_aussenluft` | Bypass Auto threshold — outdoor (°C) |
| `number.bypass_schwelle_abluft` | Bypass Auto threshold — extract (°C) |
| `number.kalibrierung_*` | Temperature sensor offsets |
| `number.party_timer_nachlauf` | Party mode duration |
| `button.filterfehler_bestatigen` | Confirm filter replacement on device |
| `button.analytics_baselines_zurucksetzen` | Reset all learned baselines |

---

## Options and calibration

Settings → Devices & Services → KWL → Configure

### Device model
Select **profi-air 250 touch** or **profi-air 400 touch**. Sets model-appropriate default watt values and activates model-specific airflow estimation.

### Power reference values
Four individually configurable watt values — one per fan level. The 400 touch defaults are actual clamp meter measurements (11 / 17.5 / 43.5 / 80 W, measured since v1.1). The 250 touch defaults are estimates — measure your own installation for accurate energy accounting.

All four values feed into cumulative energy calculation (`energy_level_X` sensors). They also drive the EC motor model: the integration derives P_base and k_aero automatically via least-squares from all four measurements, so accurate values at every level improve both the energy accounting and the real-time `power_current` accuracy.

### Poll interval
Default 30 seconds. Range 30–300 s. Shorter intervals give more accurate analytics and more responsive automations.

---

## After filter replacement

Motor RPM will shift slightly after filter replacement as the system runs against lower resistance. The analytics engine will detect this as an anomaly until it recalibrates.

After every filter replacement:
1. Press `button.kwl_analytics_baselines_zurucksetzen` to clear all learned baselines
2. Confirm the filter reset on the device (`button.kwl_filterfehler_bestatigen` or device touchscreen)
3. The analytics engine rebuilds baselines over the next 4–8 operating hours

The new baselines reflect your clean-filter state and provide a fresh reference for future degradation detection.

---

## Firmware bypass settings

The bypass has two configurable firmware thresholds in the installer section:

**For summer cooling automation users:** set both to minimum to give HA full control:
- Außenluft-Schwelle → **13°C**
- Abluft-Schwelle → **18°C**

**For users without automation:** consider raising slightly above factory defaults (15°C / 20°C) to add hysteresis. Bypass hunting at marginal temperatures accelerates actuator wear.

---

## Energy dashboard

1. Settings → Dashboards → Energy → Add Consumption
2. Add `sensor.kwl_energie_stufe_1` through `_4` as individual sources
3. Label Stufe 1 through Stufe 4

The kWh values are calculated from operating hours × configured watt values. Measure actual power at each level for best accuracy.

---

## Troubleshooting

**Integration shows unavailable**
Verify `http://YOUR_KWL_IP/status.xml` returns XML data. Check network routing if the KWL is on a different subnet.

**Installer credentials rejected**
Try factory defaults `install` / `konfig12`. If they fail, retrieve the current password from `.storage/core.config_entries` in your HA config directory.

**Bypass hunting persists after firmware threshold change**
The outdoor temperature is oscillating around the control threshold. Increase both thresholds by 2–3°C. Alternatively check the bypass actuator for mechanical stiffness or the temperature sensor for calibration drift.

**Night cooling automation does not activate**
Check `binary_sensor.kwl_sommertag` — if off, tomorrow's DWD forecast is below your threshold and indoor temperature is below 24°C. Also verify the dew point condition: `sensor.kwl_taupunkt_aussen` must be below `sensor.kwl_taupunkt_innen`.

**`analytics_maturity` low after days of operation**
Summer RPM baselines establish after ~4h each. Winter baselines require actual heating season conditions. 100% maturity is only reachable after the first complete winter. All alerts from unestablished baselines are suppressed automatically.

**Entity names are in German on an English HA**
Entity IDs are frozen at first registration per HA convention. New installations on English HA will receive English IDs from the start. Existing installations keep their German IDs — renaming them would break automations and dashboards.

---

## Known firmware behaviour

**Bypass reverts `Manuell offen` automatically**
The firmware treats `Manuell offen` as a temporary state and reverts to `Auto` within seconds. This is intentional. The summer cooling automation is designed around this: it controls fan level (stable) and relies on the firmware Auto logic for bypass, with thresholds set to their minimum values.

**Operating hours and clock drift**
The device has no NTP access. Clock drift accumulates over the device lifetime (typical 10–20% fast over 10+ years). Operating hours are accurate relative to each other and for per-level comparison; absolute values may be inflated. The maintenance alert fires on the device's own counter, which is internally consistent.

**Party mode**
Party mode activates Stufe 4 for a device-side timer. The fan entity correctly reports `Stufe 4 - Intensivlueftung` during party mode. The `kwl_sommer_kuehlung_aktiv` helper reads `on` during party mode, which is correct.

---

## Changelog

### v1.4.0

**Self-calibrating analytics engine**
New `analytics.py` — pure Python, zero HA imports. Welford online statistics per level and season. Persistent storage via `Store` with 30-minute debounced writes. Baselines: RPM per level × season, Zu/Ab ratio, η supply-side, ε exhaust-side, four-sensor energy balance, bypass episodes, night cooling events.

**New entities**
bypass_hunting, rpm_anomaly, ratio_anomaly, eta_below_baseline, fan_law_anomaly binary sensors. bypass_open_pct, bypass_avg_open_min, bypass_transitions_1h, night_cooling_last/7d, rpm_ratio, fan_law_max_deviation, spi_stufe4, eps_exhaust, energy_balance_ratio, analytics_maturity, analytics_season sensors. Analytics reset button.

**Diagnostic improvements**
motor_asymmetry threshold 25% → 22% with direction check. bypass_leaking adds summer-mode path. η gate raised 1.5K → 3.0K with seasonal context in docstring. bypass_recommended threshold aligned 2K → 3K. Unknown tags logged once only (was: every poll).

**Power and energy — EC motor model**
`power_current` uses the two-parameter EC motor model P = P_base + k × (RPM/RPM_ref)³, where P_base and k_aero are derived automatically per least-squares from the configured watt values and measured RPM ratios. For the 400 touch (measured 11/17.5/43.5/80 W): P_base = 8.93 W, k = 71.71 W, R² = 0.9989. A pure P ∝ n³ law would underestimate Stufe 1 by 72%; the EC overhead model eliminates this error. `heat_recovery_watts` uses RPM-based airflow (Q = Q_ref × RPM/RPM_ref). `fan_law_anomaly` threshold is 5% of P_Stufe4 against two-parameter residuals — was 15% against pure cubic (which would have fired falsely on every healthy motor). 400 touch watt defaults restored to measured values (11/17.5/43.5/80 W); 250 touch defaults are estimates (4/8/23/45 W).

**Configuration**
Device model selector (250 / 400 touch) in options flow. `RPM_DEFAULTS` added to const.py for use before analytics baseline is established. Translation keys activated on all entity classes for proper EN/DE support.

### v1.3.1 and earlier
See [CHANGELOG.md](CHANGELOG.md)

---

*MIT License — see [LICENSE](LICENSE)*
