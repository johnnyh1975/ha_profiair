# Changelog

Alle relevanten Änderungen an dieser Integration werden hier dokumentiert.
Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).

---

## [2.0.3] – 2026-06

### UX-Verbesserungen (systematisches UX-Review)

- **Nachtkühlungs-Kernwerte standardmäßig aktiv.** `night_cooling_last_k`
  (letzter Kühlerfolg) und `night_cooling_7d_avg_k` (7-Tage-Schnitt) sind jetzt
  standardmäßig sichtbar -- sie sind für jeden relevant, der die Sommerkühlung
  nutzt. Die drei spezielleren Diagnose-Metriken (Effizienz, inaktive Nächte,
  aktive Minuten) bleiben für die gezielte Fehlersuche deaktiviert.
- **Verständlichere Friendly Names** für 11 Diagnose-Entitäten. Fachbegriffe
  wie „WRG Abluftseite", „Analytics Reifegrad", „Spezifischer Leistungseintrag
  Stufe 4", „Fanlaufgesetz-Abweichung" wurden durch selbsterklärende Namen
  ersetzt (z.B. „Wärmerückgewinnung Abluftseite", „Selbstlernen Fortschritt",
  „Leistung pro Luftmenge (Stufe 4)", „Leistungsmodell-Anomalie"). Die
  Entity-IDs bleiben unverändert -- nur der angezeigte Name ändert sich, keine
  Automation bricht.
- **Neuer Gesamt-Energiesensor `energy_total`.** Summe des kumulativen
  Verbrauchs über alle vier Stufen -- für das HA Energy Dashboard als ein
  einziger Eintrag, statt vier `energy_level_X`-Sensoren manuell addieren zu
  müssen. Toleriert fehlende Einzelstufen (Summe der vorhandenen).
- **README: Orientierungstabelle "Welche Entität wann aktivieren".** Die ~36
  standardmäßig deaktivierten Diagnose-Entitäten haben jetzt eine klare
  Empfehlung, welche für welchen Anwendungsfall sinnvoll sind.
- **README: Beispiel-Dashboard** zum Kopieren (Steuerung, Temperaturen,
  Energie/Wartung, Nachtkühlung).
- **README: veraltete Entity-IDs korrigiert** -- die Controls-Tabelle nannte
  noch das alte `kwl_fraenkische_rohrwerke`-Schema statt `{model_slug}_{key}`.
- **Fehlende Icons ergänzt** für 8 Sensoren (Ventilator-RPM, Bypass-Status,
  Systemmeldung, Vorheizregister), die zuvor das generische Standard-Icon
  hatten.
- **Toter Geräte-Link entfernt.** Flex/flat setzte `configuration_url` auf
  `modbus://...` -- kein vom Browser öffenbares Schema. Da flex-Geräte kein
  Web-Interface haben, wird die URL jetzt weggelassen statt einen toten
  "Besuchen"-Link anzubieten.
- **Herstellername vereinheitlicht** ("Fränkische Rohrwerke" mit Umlaut, war
  beim touch-Coordinator ohne).

6 neue Tests für `energy_total` (inkl. None-Toleranz und realer Gerätewerte).
Vollständige Suite: 478/478 Tests grün.

### Code-Review-Härtung (systematisches Review)

Ein systematisches Code-Review deckte mehrere Robustheitslücken auf, primär
im Modbus-Pfad der flex/flat-Geräte:

- **Modbus-Registerlängen werden jetzt geprüft.** `_read_all_registers` und
  `_read_capabilities` validierten bislang nur `result.isError()`, nicht die
  tatsächliche Anzahl zurückgegebener Register. Manche pymodbus-Transport-
  fehler liefern eine zu kurze Registerliste *ohne* `isError()=True` — das
  hätte später beim Dekodieren zu einem ungefangenen `struct.error`/
  `IndexError` außerhalb der Fehlerbehandlung geführt und den Poll-Zyklus
  (bzw. das Setup) abstürzen lassen. Jetzt wird die Länge gegen `count`
  geprüft und sauber als `ModbusIOException` bzw. `UpdateFailed` behandelt.
- **Setup-Read abgesichert.** Die sechs harten `raw["s_*"]`-Zugriffe in
  `_read_capabilities` (System-ID, Firmware, MAC, A/B-Schalter, Referenz-RPM)
  sind durch die neue Längenprüfung garantiert sicher — ein Teil-Read führt
  jetzt zu einem sauberen Setup-Retry statt zu einem `KeyError`.
- **Timer-Cleanup vereinheitlicht.** Der Zeitsync-Timer wurde bisher manuell
  in `async_teardown` abgemeldet, der Analytics-Save-Timer über
  `async_on_unload`. Beide laufen jetzt über `async_on_unload` — ein
  einheitlicher Mechanismus, kein Risiko vergessener Abmeldungen.
- **Zeitsync-Logging gedrosselt.** Ein dauerhaft nicht erreichbares Gerät
  flutete bisher das Log mit einer Warnung pro Sync-Intervall. Jetzt: erste
  Warnung sichtbar, Folgefehler auf `debug`, plus eine Info-Meldung bei
  Wiederherstellung.
- **Diagnostics-Redaction gehärtet.** `username` wird jetzt ebenfalls
  geschwärzt, und für read-only-Touch-Setups ohne Passwort erscheint kein
  irreführender `REDACTED`-Eintrag mehr.

**Bugfix:** Die Tests für `inactive_nights()`/`avg_active_minutes()`
verwendeten feste Kalenderdaten, die aus dem rollenden 7-Tage-Fenster fielen,
sobald sie älter als 7 Tage waren. Auf relative Zeitstempel umgestellt.

4 neue Härtungstests. Vollständige Suite: 471/471 Tests grün.

### Neu: Filter-RPM-Drift-Diagnose (flex, Community-Beitrag)

Auf Basis eines Hinweises von **Torsten600**: zunehmender Filterwiderstand
zwingt die EC-Motoren bei gleicher Soll-Stufe zu höherer Drehzahl, um den
Volumenstrom zu halten. Das ist ein früherer Indikator für Filterverstopfung
als das feste zeitbasierte Filterintervall — relevant besonders in
Umgebungen mit hoher Staub- oder Pollenlast.

`filter_rpm_drift_pct` vergleicht die aktuelle RPM (bei Stufe 3) gegen die bei
der Inbetriebnahme erfasste Referenz-RPM (Register 40519/40521). Da diese
Referenz nur für Stufe 3 gilt, liefert der Sensor bei jeder anderen Stufe
bewusst `None` statt eines irreführenden Wertes. `filter_rpm_drift_warning`
feuert ab einer Abweichung von 8% (`FILTER_RPM_DRIFT_WARN_PCT`).

Beide neuen Entities sind standardmäßig deaktiviert und nur für `profi-air
flex/flat` Geräte verfügbar (Modbus-Protokoll).

### Klarstellung: Modbus-Registeradressen für Fan-RPM bestätigt

Im Rahmen der Community-Verifikation wurde ein gemeldeter Unterschied bei
den Fan-RPM-Registern (Vorschlag: Offset 162/164) gegen die offizielle
Fränkische-Modbus-XML-Dokumentation abgeglichen. Die Dokumentation bestätigt
die bereits implementierten Offsets **100/102** — keine Code-Änderung an
dieser Stelle. Die Diskrepanz wird mit dem Community-Mitwirkenden geklärt
(möglicher Firmware-Versionsunterschied).

### Tests (Stand dieser Ergänzung)

7 neue Tests für `filter_rpm_drift_pct`/`filter_rpm_drift_warning`, inklusive
des kritischen Edge-Cases "nur bei Stufe 3 gültig" und der A/B-Schalter-
Zuordnung. Vollständige Suite: 460/460 Tests grün.

### Neu: Filterverstopfungs-Verdacht (Touch + Flex, self-calibrating)

Torstens Beobachtung (zunehmender Filterwiderstand → höhere RPM bei gleicher
Stufe) ist nicht auf Modbus-Geräte mit Inbetriebnahme-Referenzregister
beschränkt — das physikalische Prinzip gilt für jedes Gerät mit Volumenstrom-
regelung. Die bereits vorhandene selbstkalibrierende RPM-Baseline pro
Stufe+Saison deckte bisher nur die entgegengesetzte Richtung ab.

**Bugfix:** `rpm_anomaly` dokumentierte eine Mindest-Stichprobengröße
(`MIN_N_RPM=500`) vor der ersten Warnung, prüfte diese aber nirgends im Code
— `WelfordEMA.z_score()` liefert bereits ab `n=2` einen Wert. Auf frischen
Installationen konnte die Warnung dadurch voreilig und potenziell falsch
feuern. Ein neues `_last_rpm_established`-Flag verfolgt jetzt korrekt, ob die
für den letzten Z-Score verwendete Baseline tatsächlich `MIN_N_RPM` Samples
erreicht hat.

**Neu:** `filter_clogging_suspected` ergänzt `rpm_anomaly` um die fehlende
Richtung (RPM signifikant *über* statt *unter* der Baseline). Beide nutzen
dieselbe Stufe+Saison-Baseline, sind aber bewusst getrennte Entities, da
unterschiedliche Ursache (Filter vs. Motor/Lager) und Handlungsempfehlung.
Funktioniert identisch für Touch- und Flex-Geräte — im Gegensatz zum
flex-spezifischen `filter_rpm_drift_pct` (fester Inbetriebnahme-Referenzwert,
nur für Stufe 3 gültig) deckt diese Diagnose alle vier Stufen ab und passt
sich automatisch an saisonale Luftdichteschwankungen an.

7 neue Tests in `test_phase7_rpm_diagnostics.py`, davon 3 explizite
Regressionstests für den `MIN_N_RPM`-Bug. Vollständige Suite: 467/467 Tests grün.

---

## [2.0.2] – 2026-06



### Fix: Nachtkühlungs-Erfolgsmessung komplett überarbeitet

**Bug:** Die session-basierte Erkennung (Stufe-4-Start bis Stufe-4-Ende)
schloss eine Session bereits beim ersten Poll der `fan_at_level_4=False`
zeigte. Da das Gerät nach ca. 2h intern auf eine niedrigere Stufe zurückfällt
und die HA-Automation dies binnen 1–11 Sekunden korrigiert, konnte ein
30s-Poll zufällig in dieses kurze Korrekturfenster fallen — die Nacht wurde
dadurch in mehrere kleine Fragmente zerrissen, von denen keines die
Mindestschwelle (0.5K) erreichte. Folge: `night_cooling_last_k` blieb
wochenlang „Unbekannt" trotz tatsächlich wirksamer Nachtkühlung.

**Fix:** `NightCoolingTracker` misst jetzt im festen Zeitfenster 22:00–07:00
Uhr direkt die Netto-Temperaturdifferenz, unabhängig von der Anzahl
zwischenzeitlicher kurzer Unterbrechungen.

**Zusätzlicher Guard:** Eine Nacht wird nur dann als Kühlerfolg gewertet,
wenn Stufe 4 im Fenster mindestens einmal aktiv war — reine natürliche
nächtliche Abkühlung ohne jede Aktivität zählt nicht als Erfolg, egal wie
groß das gemessene Delta ist.

### Neu: Aktivitäts- und Bypass-Korrelation statt reinem Delta-K

Der reine Temperaturabfall sagt nichts darüber aus, ob die Kühlstrategie
tatsächlich wirksam war oder ob die Bypass-Klappe mitgespielt hat. Neue
Metriken pro Nacht:

- **Effizienz (K/h)** — trennt echten Kühlerfolg von langer Laufzeit mit
  schwachem Ergebnis
- **Bypass-Offen-Anteil** während der aktiven Kühlzeit — deckt eine
  geschlossene oder pendelnde Bypass-Klappe auf, selbst wenn Stufe 4 lief
- **Thermisches Potenzial** (Ø T_Abluft − T_Außenluft während aktiver
  Kühlzeit) — zeigt ob die Nacht überhaupt geeignet war

### Neu: Automations-Gesundheitsmetriken

- `night_cooling_inactive_nights_7d` — Anzahl Nächte ohne jede Stufe-4-
  Aktivität in den letzten 7 Tagen. Direkte Sichtbarkeit für genau das
  Problem das den ursprünglichen Bug über Wochen verschleiert hat.
- `night_cooling_7d_avg_active_minutes` — Trend der aktiven Laufzeit über
  alle Nächte, auch ohne Kühlerfolg. Frühindikator für Automatisierungs-
  probleme, bevor sie sich im K-Wert zeigen.

### Sensor-Struktur überarbeitet

Detailwerte zum letzten Ereignis (aktive Minuten, Bypass-Anteil, thermisches
Potenzial) sind jetzt Attribute auf `night_cooling_last_k` statt eigene
Sensoren — der Recorder führt für Attribute keine Langzeitstatistik, was für
diese punktuellen Kontextwerte korrekt ist. Trend-relevante Werte
(`night_cooling_7d_avg_k`, `night_cooling_7d_avg_efficiency`,
`night_cooling_inactive_nights_7d`, `night_cooling_7d_avg_active_minutes`)
bleiben eigene Sensoren mit voller Recorder-Historie.

Alle neuen Sensoren sind standardmäßig deaktiviert (`entity_registry_enabled_default=False`).

### Tests

10 neue Tests in `test_phase6_night_cooling.py`, darunter ein expliziter
Regressionstest der das beobachtete Rückfall-Muster (kurze Unterbrechungen
durch Geräte/Automation-Korrekturzyklus) simuliert und verifiziert dass die
Session dadurch nicht mehr fragmentiert wird. Vollständige Suite: 453/453 Tests grün.

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
