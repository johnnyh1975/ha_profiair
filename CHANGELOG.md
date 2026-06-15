# Changelog

Alle relevanten Änderungen an dieser Integration werden hier dokumentiert.
Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).

---

## [2.0.0] – 2026-06

### Neu: profi-air flex und flat Unterstützung (Modbus TCP)

Diese Version fügt Unterstützung für drei neue Gerätefamilien hinzu, die über
Modbus TCP kommunizieren anstatt HTTP/XML:

| Gerät | Protokoll | Status |
|---|---|---|
| profi-air 250 touch | HTTP XML | ✅ Unverändert |
| profi-air 400 touch | HTTP XML | ✅ Unverändert |
| profi-air 250 flex | Modbus TCP | ✅ Vollständig |
| profi-air 360 flex | Modbus TCP | ✅ Vollständig |
| profi-air 180 flat | Modbus TCP | ⚠️ Experimentell |

#### Neue Entities für flex/flat

**Sensoren:** Betriebsmodus, Alarm, Raumtemperatur (T5), VOC, relative Feuchte,
CO₂, Vorheizregister-Auslastung, Bypass-Schwellenwerte, Gesamtbetriebsstunden,
Abluft-/Zuluft-RPM (flex-spezifisch)

**Steuerung:** Betriebsmodus-Select (Manuell, Bedarfsgesteuert, Wochenprogramm,
Urlaub, Sommer, Nacht, Kaminbetrieb), Filterintervall-Eingabe (30–360 Tage),
Alarm quittieren, Filterfehler bestätigen

**Diagnose:** Bypass-Leckage, Motor-Asymmetrie, Frost-Risiko, Bypass-Empfehlung
(alle shared mit touch)

**Lüftungsstufen-Steuerung** (Lüfter-Entity) für flex ist noch **nicht verfügbar**
— das FC16-Schreibformat für Stufenänderungen wird noch bestätigt.
Kommt als v2.0.1 sobald bestätigt.

#### Polling-Strategie (Modbus)

Zweiteiliges Polling: operative Register (Temperaturen, RPM, Stufe, Alarm,
Modus) bei jedem Poll-Zyklus; quasi-statische Register (Filterlaufzeit,
Bypass-Schwellenwerte, Betriebsstunden) alle 10 Zyklen (~5 min bei 30 s
Standardintervall). Schreibbefehle lösen sofort einen Refresh aus.

#### Setup

Protokoll-Erkennung vollautomatisch: HTTP-Probe zuerst (touch), dann Modbus-
Probe (flex). Kein manuelles Protokoll-Auswählen nötig.

Installateur-Zugangsdaten für touch-Geräte sind jetzt optional — "Überspringen"
ermöglicht Lese-only-Betrieb ohne Installer-Passwort.

---

### Geändert

- **Lüfter-Entity** (touch): Anzeigename ist jetzt der Gerätename ohne Suffix
  "Lüftung" (`_attr_name = None`, HA-Hauptentity-Muster)
- **Config Flow VERSION**: 3 → 4 (automatische Migration bestehender Einträge)
- **Options Flow**: Protokoll-bewusst — flex zeigt optionale Watt-Felder ohne
  Pflichtmodus, touch behält bisherigen Modell-Selektor

### Migration (v1.4.x → v2.0.0)

Bestehende touch-Einträge werden automatisch migriert:
1. `CONF_PROTOCOL = "http"` wird in `entry.data` ergänzt
2. Fan-Entity-ID `fan.{model}_fan` → `fan.{model}` (falls vorhanden)

Kein manueller Eingriff nötig. Die Migration läuft beim ersten Start nach dem Update.

---

## [1.4.0] – 2025

### Neu

- Self-kalibrierende Analytics-Engine (`KWLAnalytics`) mit Welford-Algorithmus
- Dynamische Leistungsberechnung (EC-Motor-Modell P = P_base + k × (n/n_ref)³)
- Diagnostik-Entities: Bypass-Leckage, Motor-Asymmetrie, Bypass-Empfehlung
- Gerätemodell-Auswahl (250 touch / 400 touch) im Options Flow
- Vollständige DE/EN Übersetzungsunterstützung
- Sommer/Winter-Baselines (48h-EMA Außentemperatur, 10°C Schwelle)
- Erste-Winter-Alarmierung für ε_exhaust und Energiebilanz

---

## [1.3.1] – 2025

### Neu

- Abgeleitete Diagnose-Sensoren (Wärmerückgewinnungsgrad, Frost-Risiko)
- Options Flow mit Scan-Intervall und Watt-Konfiguration
- Übersetzungen DE/EN
- Automation-Beispiele in der Dokumentation

---

## [1.1.x] – 2025

### Behoben

- Kritische `AttributeError`-Regression bei fehlenden XML-Tags behoben
- Robusteres XML-Parsing bei unvollständigen Antworten

---

## [1.0.0] – 2024

### Erstveröffentlichung

- Unterstützung für profi-air 250/400 touch (HTTP XML)
- Grundlegende Sensor-Entities (Temperaturen, RPM, Lüftungsstufe)
- Lüfter-Entity mit Stufen 1–4
- Config Flow mit Installateur-Authentifizierung
- HACS-Distribution
