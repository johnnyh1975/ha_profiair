# Changelog

Alle relevanten Änderungen an dieser Integration werden hier dokumentiert.
Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).

---

## [2.0.1] – 2026-06

### Neu: Lüftungsstufen-Steuerung für flex/flat

`async_set_level()` ist jetzt implementiert (zuvor `NotImplementedError`).
`prmRomIdxSpeedLevel` ist als UINT32 dokumentiert (2×16-Bit-Register,
40325+40326) — FC06 (Write Single Register) kann nur ein 16-Bit-Wort
schreiben und scheitert daher erwartungsgemäß; FC16 (Write Multiple
Registers) schreibt beide Wörter atomar, exakt das Muster das bereits für
Modus, Filter-Reset, Alarm-Clear und Filter-Intervall verwendet wird. Die
Implementierung wechselt automatisch in den Manual-Mode, falls das Gerät
sich in einem anderen Betriebsmodus befindet (Stufenänderungen werden laut
Gerätedokumentation nur im Manual-Mode übernommen).

Die Fan-Entity ist jetzt für flex/flat-Geräte verfügbar — der bisherige
Protocol-Guard in `fan.py` wurde entfernt, da `KWLFan` ohne Änderung für
beide Coordinator-Typen funktioniert.

> **Hinweis:** Implementiert nach dokumentiertem Register-Verhalten, noch
> nicht an echter flex/flat-Hardware validiert. Feedback von Testern
> willkommen.

### Behoben

- **Diagnose-Genauigkeit beim Setup (flex/flat):** Drei zuvor identische
  Fehlermeldungen ("Nicht erreichbar") sind jetzt unterscheidbar:
  TCP-Verbindung fehlgeschlagen, verbunden aber keine Antwort auf
  Register-Abfrage (`modbus_no_response` — deutet auf deaktiviertes
  Modbus TCP oder falsche Slave-ID hin), und verbunden mit unbekanntem
  Gerätetyp-Code (`unknown_device_type`, zeigt den Code direkt an).
- **Ungefangene Exception bei Verbindungs-Timeout (touch):** `_fetch_device_info`
  und `_test_auth` fingen nur `aiohttp.ClientError` ab. Ein Timeout (Gerät
  antwortet gar nicht, z. B. bei nicht erreichbarer IP) wirft
  `asyncio.TimeoutError`, was kein `ClientError` ist — die Exception lief
  unbehandelt durch und HA zeigte "Unknown error occurred" statt einer
  brauchbaren Meldung. Beide Funktionen fangen jetzt zusätzlich
  `TimeoutError` ab.
- **Modell-Selektor zeigte Rohwerte:** Die Options-Flow-Modellauswahl zeigte
  `profi_air_250`/`profi_air_400` statt Klarnamen. Auf `SelectSelector` mit
  `MODEL_DISPLAY`-Labels umgestellt.
- **`night_cooling_last_k`/`night_cooling_7d_avg_k` zeigten wochenlang
  "Unbekannt":** Diese Sensoren haben erst nach dem ersten qualifizierenden
  Nachtkühlungs-Ereignis einen Wert (Stufe 4 + messbarer Temperaturabfall).
  Jetzt standardmäßig deaktiviert, analog zu den anderen Analytics-Sensoren
  mit Einlaufzeit.

### Bekannte offene Punkte

- Watt-Messwerte (Klammermessung) für profi-air 250 flex und 360 flex stehen
  weiterhin aus.

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
