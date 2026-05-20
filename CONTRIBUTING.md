# Contributing

Danke für dein Interesse an der KWL Fränkische Rohrwerke Integration!

## Entwicklungsumgebung einrichten

```bash
git clone https://github.com/johnnyh1975/ha-kwl-fraenkische
cd ha-kwl-fraenkische
pip install -r requirements_test.txt
```

## Tests ausführen

```bash
pytest tests/ -v
```

## Änderungen einreichen

1. Fork erstellen
2. Feature Branch anlegen (`git checkout -b feature/meine-aenderung`)
3. Änderungen committen (`git commit -m 'Beschreibung'`)
4. Branch pushen (`git push origin feature/meine-aenderung`)
5. Pull Request öffnen

## Code-Standards

- Alle neuen Funktionen brauchen Tests
- Type Annotations für alle Funktionen
- HA Integration Quality Scale Platinum Standards einhalten
- Imports: stdlib → third-party → homeassistant → lokale Module

## Geräte-Kompatibilität

Getestet mit Fränkische Rohrwerke Profi-Air 400.
Bei anderen Modellen bitte Issue öffnen mit `status.xml` Beispiel.
