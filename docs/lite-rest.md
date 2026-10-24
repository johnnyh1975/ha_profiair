# profi-air 140 / 200 lite — REST/JSON (experimentell)

> **Status: experimentell.** Die Unterstützung wurde aus der Analyse der
> Hersteller-App „profi-air smart control“ 1.2.6 abgeleitet und gegen einen
> lokalen Mock-Server getestet, der sich so verhält, wie die App es erwartet.
> **Sie wurde noch nicht an einem echten 140/200 lite geprüft.** Feldnamen,
> Skalierungen und die Frage, ob das Gerät Schreibbefehle lokal annimmt, sind
> unbestätigt.

## Was das für ein Gerät ist

Der 140/200 lite hat kein Modbus und keine Touch-Weboberfläche. Er trägt ein
WLAN-Modul (ESP8266) der Firma Innova mit einer REST/JSON-API unter
`http://<ip>/api/v/1/` — ohne Verschlüsselung und ohne lokale Anmeldung. Die
Geräteklasse meldet sich mit `deviceType "002"` (Innova „AirLeaf“-Familie).

Die Hersteller-App bedient das Gerät im Heimnetz über die Innova-Cloud; Status,
Einrichtung und Registerzugriff gehen direkt an die IP. Diese Integration
verwendet **ausschließlich die lokale API** und benötigt keine Cloud.

**Grundsatz: lokal hat Priorität.** Es gibt keinen Cloud-Code, keine
Cloud-Zugangsdaten und keinen stillen Fallback. Lehnt das Gerät einen
`set/*`-Befehl lokal ab, wird das als Fehler gemeldet (HA-Fehlermeldung,
Diagnosedaten) und nicht über die Cloud umgangen. Eine Cloud-Option käme nur
als bewusst aktivierbare Ergänzung in Frage, falls Tests sie nötig machen.

## Was die Integration bietet

| Entität | Quelle (`RESULT`) | Hinweis |
|---|---|---|
| Lüftung (Fan) Ein/Aus | `ps`, Befehl `power/on\|off` | „Ein“ gilt nur, wenn zugleich kein Fensterkontakt (`CP`) sperrt — so wertet es auch die App |
| Lüftungsfunktion | `fn` (1–4), Befehl `set/function/auto\|night\|min\|max` | als Preset-Modus: Auto, Nacht, Minimal, Maximal |
| Raumtemperatur | `ta` ÷ 10 | °C |
| Raumfeuchte | `humidity` ÷ 10 | %, nur wenn > 0 |
| Luftqualität | `airQuality` | Stufe 1–5 = `round(Rohwert ÷ 100)`, mindestens 1 (wie die App) |
| Registertemperatur | `tw` ÷ 10 | standardmäßig deaktiviert; `< 0` = nicht vorhanden |
| Alarme | `a` (Liste) | Text und „Alarm aktiv“ (ohne reine Kontaktanwesenheit) |
| Kontakt (Fenster) aktiv | `a` enthält `CP` | Gerät ist dann gesperrt |
| Tastensperre (Schalter) | `kl`, Befehl `set/lock/on\|off` | schreibbar |
| Sollwert (Zahl) | `sp` ÷ 10, Befehl `set/setpoint` mit `{"temp": °C × 10}` | 5–40 °C, Schritt 0,5, begrenzt durch `spl`/`sph`; **standardmäßig deaktiviert** |
| Betriebsart (Auswahl) | `wm` (3 = Winter, 5 = Sommer), Befehl `set/mode/heating\|cooling` | schaltet das Gerät zuerst ein, wie `innova-controls`; **standardmäßig deaktiviert** |

Nicht verfügbar über diese Schnittstelle: Volumenstrom, Lüfterdrehzahl,
Filter, Bypass, Außen-/Fortlufttemperatur, Energie. Es gibt daher weder
Stufen noch Leistungsberechnung noch Analytics.

Bewusst **nicht** umgesetzt:

- `rs485/write`, `setup`, `network/set` — sie schreiben Geräteregister bzw.
  Netzwerkkonfiguration und könnten das Gerät unbrauchbar machen. Ein Test
  stellt sicher, dass der Client keine solche Methode anbietet.
- Wochenprogramm (`calendar/*`) und Uhr setzen (`set/time`): brauchen laut App
  die Cloud-Einrichtung bzw. sind für ein Lüftungsgerät nicht belegt.

Sollwert und Betriebsart wirken laut App nur mit „Hydronik-Batterie“
(Wasser-Register); ob und wie das beim lite-Lüftungsgerät relevant ist, ist
unbekannt. Deshalb sind beide Entitäten zunächst deaktiviert und müssen von
Hand aktiviert werden.

## Wire-Format (so wie die App es sendet)

- Lesen: `GET /api/v/1/status` → `{"success": true, "deviceType": "002",
  "UID": "…", "RESULT": {…}, "setup": {"serial", "name"}, "sw": {"V"},
  "net": {"ip", …}}`
- Schreiben: `POST`, Body = JSON-**String** (`{"value":1}`), Header
  `Content-Type: application/x-www-form-urlencoded` (Eigenheit der App; der
  ESP-Server toleriert das offenbar). Ein-/Ausschalten ohne Body.
- Antworten sind JSON mit `success`; bei Fehlern `error` = `E0xx`.

## Erkennung beim Einrichten

Der Config Flow probiert: touch (`/status.xml`) → lite (`GET /api/v/1/status`,
muss `success: true` und `deviceType` leer oder `"002"` liefern) → Modbus. Die
eindeutige ID ist `UID`, sonst die Seriennummer, sonst die IP.

## So hilfst du bei der Validierung

1. Integration einrichten (IP des WLAN-Moduls).
2. **Einstellungen → Geräte & Dienste → KWL → Diagnose herunterladen.** Die
   Datei enthält das rohe `RESULT` des Geräts (Seriennummer, UID, Name und IP
   sind entfernt bzw. nicht enthalten). Bitte im GitHub-Issue anhängen.
3. Prüfen und berichten:
   - Stimmen Raumtemperatur, Feuchte und Luftqualität mit dem Gerätedisplay
     bzw. der App überein?
   - Wirken **Auto/Nacht/Min/Max** und **Ein/Aus** aus Home Assistant am Gerät?
     (Offen: ob das Gerät diese Befehle lokal annimmt, während die App sie über
     die Cloud schickt.)
   - Welche Werte stehen im Alarm-Feld `a`, wenn ein Fenster geöffnet ist?
   - Gibt es Felder in `raw_result`, die die Integration nicht nutzt, aber
     nützlich wären?

Ohne diese Rückmeldungen bleibt die Unterstützung experimentell.

## Quellen und Grenzen

- Analyse der App „profi-air smart control“ 1.2.6 (WebView-JavaScript und native
  DEX-Klassen). Alle Aussagen beschreiben, was die **App** tut — nicht
  zwingend, was die Firmware akzeptiert.
- Die Python-Bibliothek `innova-controls` 2.2.4 (PyPI, Apache-2.0) spricht
  dieselbe lokale API für AirLeaf-Geräte. Ihr Quellcode bestätigt unabhängig
  von der App die Endpunkte, Funktionscodes (`fn` 1–4), Betriebsartcodes (`wm`
  3/5) und die Statusfelder `ps`, `ta`, `tw`, `sp`, `kl`, `cm` samt Skalierung
  ÷ 10. Sie wurde als Referenz herangezogen, aber **nicht** als Abhängigkeit
  eingebunden: Einzelentwickler, nur an einem Innova-2.0-Gerät getestet, unbekannte
  `deviceType` fallen auf „2.0“ zurück (die lite-App nimmt `002` an), `fn = 0`
  löst dort einen `KeyError` aus, Fehler werden verschluckt, und sie kennt weder
  Feuchte, Luftqualität noch Alarme.
- Die Bibliothek maskiert `RESULT["pwd"]`: Die Statusantwort kann ein
  Passwortfeld enthalten. Diese Integration maskiert Felder mit `pwd`/`pass` im
  Namen in `raw_result` und im Datenobjekt.
