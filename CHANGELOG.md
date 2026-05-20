# Changelog

Alle wichtigen Änderungen an dieser Integration werden in dieser Datei dokumentiert.

Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).
Die Versionierung folgt [Semantic Versioning](https://semver.org/lang/de/).

---

## [1.0.0] - 2026-05-19

### Hinzugefügt
- Lüftungsstufen 1–4 als Fan-Entity mit Prozent-Schieberegler und Preset-Modi
- Automatische Zeitsynchronisation (Start + alle 24 h) inkl. Sommer-/Winterzeit
- Energie-Dashboard: kumulativer kWh-Verbrauch pro Stufe (basierend auf Betriebsstunden)
- Vollständiges Sensor-Mapping: Temperaturen, Motor-RPM, Motorspannung, Wärmerückgewinnung
- Bypass-Steuerung: Manuell offen / Manuell zu / Automatisch
- Temperaturkorrekturen für alle vier Messfühler (±4.9 °C)
- Luftmengen-Konfiguration pro Stufe (Experten, standardmäßig deaktiviert)
- Haustyp, Vorheizregister, Safety Manager über Select-Entities konfigurierbar
- Ext. Sensor-Typen (Feuchte %H / CO2 ppm) konfigurierbar
- HTTP Basic Auth für den Installateur-Bereich
- Optimistic Updates — UI reagiert sofort ohne Wartezeit
- Re-Auth Flow bei abgelaufenen Zugangsdaten (ConfigEntryAuthFailed)
- Reconfigure Flow — IP und Zugangsdaten ohne Neueinrichtung änderbar
- Konfigurierbare Nennleistung pro Stufe im Setup-Wizard (Standardwerte: 11/17.5/43.5/80 W)
- Diagnostics mit automatischem Redacting sensitiver Daten
- Repair Issue für Filterwechsel-Alarm mit automatischer Quittierung
- 117 automatisierte Tests (Unit + Config Flow)
- Vollständige Übersetzungen: Deutsch und Englisch
- HACS-kompatibel mit GitHub Actions CI (HACS Validation + Hassfest)
- Quality Scale: 🏆 Platinum

### Technische Details
- `entry.runtime_data` Pattern (HA 2024.4+)
- `async_get_clientsession(hass)` statt eigener aiohttp Session
- `DataUpdateCoordinator` mit `config_entry=entry` (HA 2025.11 Deadline)
- `@dataclass(frozen=True, kw_only=True)` für alle EntityDescriptions (HA 2025.1+)
- `PARALLEL_UPDATES` konfiguriert: 1 für schreibende, 0 für lesende Plattformen
- Minimale HA-Version: 2026.3

---

## [Unveröffentlicht]

Keine ausstehenden Änderungen.
