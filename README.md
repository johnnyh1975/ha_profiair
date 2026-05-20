# KWL Fränkische Rohrwerke — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2026.3%2B-blue.svg)](https://www.home-assistant.io/)
[![Quality Scale](https://img.shields.io/badge/Quality%20Scale-Gold-gold.svg)](https://developers.home-assistant.io/docs/core/integration-quality-scale/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Macht die **Fränkische Rohrwerke KWL** (Profi-Air) smart — ohne Cloud, ohne externen Dienst, ausschließlich über das lokale Netzwerk.

![Fränkische Rohrwerke](brand/logo.png)

---

## Funktionen

- **Lüftungsstufen 1–4** steuerbar als Fan-Entity mit Prozent-Schieberegler und Preset-Modi
- **Automatische Zeitsynchronisation** — beim Start und alle 24 Stunden, inkl. Sommer-/Winterzeit
- **Energie-Dashboard** — kumulativer kWh-Verbrauch pro Stufe basierend auf Betriebsstunden
- **Vollständiges Sensor-Mapping** — Temperaturen, Motor-RPM, Motorspannung, Wärmerückgewinnung
- **Bypass-Steuerung** — Manuell offen / Manuell zu / Automatisch
- **Temperaturkorrekturen** für alle vier Messfühler
- **HTTP Basic Auth** für den geschützten Installateur-Bereich
- **Optimistic Updates** — UI reagiert sofort ohne auf den nächsten Poll zu warten
- **Re-Auth Flow** — automatische Aufforderung bei abgelaufenen Zugangsdaten
- **Rekonfigurierung** — IP-Adresse und Zugangsdaten ohne Neueinrichtung änderbar

---

## Unterstützte Geräte

Getestet mit der **Fränkische Rohrwerke Profi-Air** KWL-Anlage mit integriertem Webserver.

Das Gerät muss über HTTP erreichbar sein (Standard: `http://10.10.4.1`). Eine Internetverbindung ist nicht erforderlich.

---

## Installation

### Über HACS (empfohlen)

1. HACS öffnen → Integrationen → ⋮ → Benutzerdefinierte Repositories
2. URL eintragen: `https://github.com/johnnyh1975/ha-kwl-fraenkische`
3. Kategorie: Integration → Hinzufügen
4. Integration suchen und installieren
5. Home Assistant neu starten

### Manuell

1. Den Ordner `custom_components/kwl_fraenkische/` in dein HA-Konfigurationsverzeichnis kopieren
2. Home Assistant neu starten

---

## Einrichtung

1. **Einstellungen → Geräte & Dienste → Integration hinzufügen**
2. Nach **KWL Fränkische Rohrwerke** suchen
3. **Schritt 1:** IP-Adresse der KWL eingeben (Standard: `10.10.4.1`)
4. **Schritt 2:** Installateur-Zugangsdaten eingeben
   - Benutzer: `install`
   - Passwort: `konfig12` *(Werkseinstellung — bitte ändern!)*

> ⚠️ **Sicherheitshinweis:** Die Werkseinstellungen (`install` / `konfig12`) sind öffentlich bekannt. Bitte das Passwort direkt am Gerät unter `http://10.10.4.1/setup.htm` ändern.

### Neu konfigurieren

IP-Adresse oder Zugangsdaten können ohne Neueinrichtung geändert werden:
**Einstellungen → Geräte & Dienste → KWL → ⋮ → Neu konfigurieren**

---

## Entities

### Fan
| Entity | Beschreibung |
|--------|-------------|
| `fan.kwl_lueftung` | Lüftungssteuerung mit Stufe 1–4, Prozent und Preset-Modus |

**Preset-Modi:**
| Preset | Stufe | Prozent | Leistung (gemessen) |
|--------|-------|---------|---------------------|
| Stufe 1 – Feuchteschutz | 1 | 25% | 11 W |
| Stufe 2 – Reduziert | 2 | 50% | 17.5 W |
| Stufe 3 – Nennlüftung | 3 | 75% | 43.5 W |
| Stufe 4 – Intensivlüftung | 4 | 100% | 80 W |

### Sensoren
| Entity | Beschreibung | Einheit |
|--------|-------------|---------|
| `sensor.kwl_abluft_temperatur` | Ablufttemperatur (Innenluft) | °C |
| `sensor.kwl_zuluft_temperatur` | Zulufttemperatur (nach Wärmetauscher) | °C |
| `sensor.kwl_aussenluft_temperatur` | Außenlufttemperatur | °C |
| `sensor.kwl_fortluft_temperatur` | Fortlufttemperatur (raus) | °C |
| `sensor.kwl_zuluft_motor_u_min` | Zuluftmotor Drehzahl | rpm |
| `sensor.kwl_abluft_motor_u_min` | Abluftmotor Drehzahl | rpm |
| `sensor.kwl_zuluft_motor_spannung` | Zuluftmotor Spannung | V |
| `sensor.kwl_abluft_motor_spannung` | Abluftmotor Spannung | V |
| `sensor.kwl_aktuelle_leistung` | Aktuelle Leistungsaufnahme | W |
| `sensor.kwl_energie_stufe_1` | Kumulativer Verbrauch Stufe 1 | kWh |
| `sensor.kwl_energie_stufe_2` | Kumulativer Verbrauch Stufe 2 | kWh |
| `sensor.kwl_energie_stufe_3` | Kumulativer Verbrauch Stufe 3 | kWh |
| `sensor.kwl_energie_stufe_4` | Kumulativer Verbrauch Stufe 4 | kWh |
| `sensor.kwl_aktuelle_stufe` | Aktuelle Stufe als Text | — |
| `sensor.kwl_bypass_status` | Bypass-Status | — |
| `sensor.kwl_systemmeldung` | Aktuelle Systemmeldung | — |
| `sensor.kwl_party_timer_restzeit` | Party-Timer Restzeit | min |

**Standardmäßig deaktiviert** (aktivierbar unter Einstellungen → Geräte):
| Entity | Beschreibung | Einheit |
|--------|-------------|---------|
| `sensor.kwl_betriebsstunden_stufe_1` | Betriebsstunden Stufe 1 | h |
| `sensor.kwl_betriebsstunden_stufe_2` | Betriebsstunden Stufe 2 | h |
| `sensor.kwl_betriebsstunden_stufe_3` | Betriebsstunden Stufe 3 | h |
| `sensor.kwl_betriebsstunden_stufe_4` | Betriebsstunden Stufe 4 | h |
| `sensor.kwl_betriebsstunden_frostschutz` | Betriebsstunden Frostschutz | h |
| `sensor.kwl_betriebsstunden_vorheizregister` | Betriebsstunden Vorheizregister | h |

### Binary Sensoren
| Entity | Beschreibung |
|--------|-------------|
| `binary_sensor.kwl_filter_ok` | Filterstatus (Problem = Filter wechseln) |
| `binary_sensor.kwl_safety_manager` | Safety Manager aktiv |
| `binary_sensor.kwl_passivhaus_modus` | Passivhaus-Modus aktiv |
| `binary_sensor.kwl_vorheizregister_aktiv` | Vorheizregister aktiv |

### Einstellungen (Number)
| Entity | Beschreibung | Bereich |
|--------|-------------|---------|
| `number.kwl_party_timer_nachlauf` | Party-Timer Dauer | 10–240 min |
| `number.kwl_bypass_schwelle_aussenluft` | Bypass-Auslösung Außenluft | 13–18 °C |
| `number.kwl_bypass_schwelle_abluft` | Bypass-Auslösung Abluft | 18–25 °C |
| `number.kwl_kalibrierung_abluft` | Temperaturkorrektur Abluft | ±4.9 °C |
| `number.kwl_kalibrierung_zuluft` | Temperaturkorrektur Zuluft | ±4.9 °C |
| `number.kwl_kalibrierung_fortluft` | Temperaturkorrektur Fortluft | ±4.9 °C |
| `number.kwl_kalibrierung_aussenluft` | Temperaturkorrektur Außenluft | ±4.9 °C |

**Standardmäßig deaktiviert** (nur für Experten):
| Entity | Beschreibung | Bereich |
|--------|-------------|---------|
| `number.kwl_luftmenge_stufe_*_zuluft` | Lüfterleistung Zuluft je Stufe | 0–10 V |
| `number.kwl_luftmenge_stufe_*_abluft` | Lüfterleistung Abluft je Stufe | 0–10 V |

### Auswahl (Select)
| Entity | Optionen |
|--------|---------|
| `select.kwl_bypass_steuerung` | Manuell offen / Manuell zu / Automatisch |
| `select.kwl_haustyp` | Eigenheim / Mietwohnung |
| `select.kwl_vorheizregister_modus` | Aktiv / Passiv |
| `select.kwl_safety_manager` | Mit / Ohne |
| `select.kwl_ext_sensor_1_typ` | Keiner / Feuchte (%H) / CO2 (ppm) |
| `select.kwl_ext_sensor_2_typ` | Keiner / Feuchte (%H) / CO2 (ppm) |
| `select.kwl_ext_sensor_3_typ` | Keiner / Feuchte (%H) / CO2 (ppm) |
| `select.kwl_ext_sensor_4_typ` | Keiner / Feuchte (%H) / CO2 (ppm) |

### Buttons
| Entity | Beschreibung |
|--------|-------------|
| `button.kwl_filterfehler_bestaetigen` | Filterwechsel-Alarm quittieren |
| `button.kwl_externe_sensoren_umschalten` | Externe Sensoren ein-/ausschalten |

---

## Energie-Dashboard

Die vier Energie-Sensoren können direkt im HA Energie-Dashboard als **Individuelle Geräte** eingetragen werden. HA summiert den Tages- und Monatsverbrauch automatisch.

**Einstellungen → Energie → Individuelle Geräte → Gerät hinzufügen:**
- `sensor.kwl_energie_stufe_1`
- `sensor.kwl_energie_stufe_2`
- `sensor.kwl_energie_stufe_3`
- `sensor.kwl_energie_stufe_4`

---

## Automatisierungsbeispiele

### Lüftung bei hoher CO2-Konzentration hochschalten
```yaml
automation:
  triggers:
    - trigger: numeric_state
      entity_id: sensor.co2_wohnzimmer
      above: 1000
  actions:
    - action: fan.set_preset_mode
      target:
        entity_id: fan.kwl_lueftung
      data:
        preset_mode: "Stufe 3 - Nennlueeftung"
```

### Sommer-Nacht-Vorkühlung (Bypass + Stufe 3)
```yaml
automation:
  alias: "KWL Bypass Sommer-Kühlung"
  triggers:
    - trigger: time
      at: "22:00:00"
  conditions:
    - condition: numeric_state
      entity_id: sensor.kwl_abluft_temperatur
      above: 22
    - condition: template
      value_template: >
        {{ states('sensor.kwl_aussenluft_temperatur') | float(0)
           < states('sensor.kwl_abluft_temperatur') | float(0) - 2 }}
  actions:
    - action: select.select_option
      target:
        entity_id: select.kwl_bypass_steuerung
      data:
        option: "Manuell offen"
    - action: fan.set_preset_mode
      target:
        entity_id: fan.kwl_lueftung
      data:
        preset_mode: "Stufe 3 - Nennlueeftung"
```

### Benachrichtigung bei Filterproblem
```yaml
automation:
  triggers:
    - trigger: state
      entity_id: binary_sensor.kwl_filter_ok
      to: "on"
  actions:
    - action: notify.mobile_app
      data:
        message: "KWL: Filter muss gewechselt werden!"
```

---

## HTTP-Endpunkte

| Endpunkt | Methode | Auth | Beschreibung |
|----------|---------|------|-------------|
| `/status.xml` | GET | — | Alle Statuswerte (Poll alle 30 s) |
| `/stufe.cgi?stufe=N` | GET | — | Lüftungsstufe 1–4 setzen |
| `/setup.htm` | POST | — | Benutzereinstellungen |
| `/time.htm` | POST | — | Zeitsynchronisation |
| `/filter.cgi?filter=1` | GET | — | Filterfehler quittieren |
| `/sensor.cgi?sensor=1` | GET | — | Externe Sensoren umschalten |
| `/install/install.htm` | POST | Basic Auth | Installateureinstellungen |

---

## Fehlerbehebung

### Integration taucht nicht auf
Entwicklerwerkzeuge → YAML → Template-Entities neu laden, dann HA neu starten.

### Verbindungsfehler bei der Einrichtung
- KWL und HA müssen im gleichen Netzwerk sein
- Browser-Test: `http://10.10.4.1/status.xml` muss XML zurückgeben
- Bei Docker: Netzwerkmodus `host` prüfen

### Entity bleibt `unavailable`
```bash
curl -s http://10.10.4.1/status.xml | head -5
```
Gibt das XML zurück? Wenn nein, ist die KWL nicht erreichbar.

### Falsche Zugangsdaten (401)
HA zeigt automatisch einen Re-Auth Dialog. Alternativ:
**Einstellungen → Geräte & Dienste → KWL → ⋮ → Neu authentifizieren**

### Diagnose herunterladen
**Einstellungen → Geräte & Dienste → KWL → ⋮ → Diagnose herunterladen**
Sensitive Daten (Passwort, MAC) werden automatisch geschwärzt.

---

## Bekannte Einschränkungen

- Die KWL kann **nicht ausgeschaltet** werden — Stufe 1 ist der Mindestbetrieb
- Der Wochenplan des Geräts wird nicht in HA abgebildet — besser HA-Automationen nutzen
- Externe Sensoren (CO2, Feuchte) werden nur angezeigt wenn am Gerät angeschlossen und konfiguriert
- Auto-Discovery nicht möglich — die KWL hat kein mDNS/SSDP

---

## Changelog

### v0.1.0 (2026-05)
- Erstveröffentlichung
- Lüftungsstufen 1–4 als Fan-Entity mit Prozent und Preset-Modi
- Vollständiges Sensor-Mapping (Temperaturen, Motor, Energie)
- Bypass-Steuerung, Temperaturkorrekturen, Luftmengen-Einstellung
- Automatische Zeitsynchronisation mit DST
- HTTP Basic Auth für Installateur-Bereich
- Re-Auth Flow und Reconfigure Flow
- 109 Unit-Tests

---

## Lizenz

MIT License — siehe [LICENSE](LICENSE)
