"""Konstanten für die KWL Fränkische Rohrwerke Integration."""
DOMAIN = "kwl_fraenkische"

# ── Protokoll ─────────────────────────────────────────────────────────────────

CONF_PROTOCOL = "protocol"
PROTOCOL_HTTP    = "http"    # profi-air 250/400 touch (HTTP XML)
PROTOCOL_MODBUS  = "modbus"  # profi-air 250/360 flex, 180 flat (Modbus TCP)

# ── Gerätemodelle ─────────────────────────────────────────────────────────────

CONF_MODEL = "model"
MODEL_PROFI_AIR_250 = "profi_air_250"
MODEL_PROFI_AIR_400 = "profi_air_400"
DEFAULT_MODEL = MODEL_PROFI_AIR_400

# Flex-Modelle (Modbus TCP, UVC Controller)
MODEL_PROFI_AIR_250_FLEX = "profi_air_250_flex"
MODEL_PROFI_AIR_360_FLEX = "profi_air_360_flex"
MODEL_PROFI_AIR_180_FLAT = "profi_air_180_flat"  # Experimentell: kein validierter Messwert

# Protokoll-Zuordnung pro Modell-Familie
MODEL_PROTOCOLS: dict[str, str] = {
    MODEL_PROFI_AIR_250:      PROTOCOL_HTTP,
    MODEL_PROFI_AIR_400:      PROTOCOL_HTTP,
    MODEL_PROFI_AIR_250_FLEX: PROTOCOL_MODBUS,
    MODEL_PROFI_AIR_360_FLEX: PROTOCOL_MODBUS,
    MODEL_PROFI_AIR_180_FLAT: PROTOCOL_MODBUS,
}

# UVC Controller prmSystemID Byte 0 → Modell
# Quelle: Fränkische UVC Controller Modbus TCP/IP Doku, Rev. 3.b
UNIT_TYPE_TO_MODEL: dict[int, str] = {
    4:  MODEL_PROFI_AIR_180_FLAT,   # Experimentell
    11: MODEL_PROFI_AIR_250_FLEX,
    15: MODEL_PROFI_AIR_360_FLEX,
}

# Anzeige-Name pro Modell (für device_info und Config Flow Bestätigung)
MODEL_DISPLAY: dict[str, str] = {
    MODEL_PROFI_AIR_250:      "Profi-Air 250 touch",
    MODEL_PROFI_AIR_400:      "Profi-Air 400 touch",
    MODEL_PROFI_AIR_250_FLEX: "profi-air 250 flex",
    MODEL_PROFI_AIR_360_FLEX: "profi-air 360 flex",
    MODEL_PROFI_AIR_180_FLAT: "profi-air 180 flat (experimentell)",
}

# EC-Motor-Modell: P = P_base + k × (RPM/RPM_max)³
#   P_base ≈ 8.93 W  (Steuerelektronik + Mindesterregung, konstant)
#   k ≈ 71.71 W      (aerodynamischer Anteil bei Vollast)
#   → Reines P ∝ n³ unterschätzt bei Stufe 1 um 72 % — nicht verwenden.
#
# Flex-Modelle: None = ausstehend (Klammermessung noch nicht vorhanden).
# Werte werden eingetragen sobald Torsten600 gemessen hat.
WATT_DEFAULTS: dict[str, dict[int, float | None]] = {
    MODEL_PROFI_AIR_250: {1: 4.0,  2: 8.0,  3: 23.0, 4: 45.0},
    MODEL_PROFI_AIR_400: {1: 11.0, 2: 17.5, 3: 43.5, 4: 80.0},
    # Flex: Klammermessungen ausstehend → None bis Werte vorliegen
    MODEL_PROFI_AIR_250_FLEX: {1: None, 2: None, 3: None, 4: None},
    MODEL_PROFI_AIR_360_FLEX: {1: None, 2: None, 3: None, 4: None},
    MODEL_PROFI_AIR_180_FLAT: {1: None, 2: None, 3: None, 4: None},
}

# Maximale Gesamtleistung beider Lüfter (aus Datenblatt, ohne Defroster)
# Wird im Options Flow als Obergrenze-Validator genutzt.
# Flex: Datenblatt-Werte. Touch: kein Datenblatt-Limit definiert.
WATT_MAX: dict[str, float] = {
    MODEL_PROFI_AIR_250_FLEX: 170.0,
    MODEL_PROFI_AIR_360_FLEX: 230.0,
    # 180 flat: kein validierter Wert → kein Validator
}

# Typische Abluft-RPM pro Stufe (gemessen, 400er Installation, st1a=2.1V..st4a=6.5V)
# Wird für EC-Motor-Modell verwendet wenn keine Analytics-Baseline verfügbar.
RPM_DEFAULTS: dict[int, float] = {1: 858.0, 2: 1257.0, 3: 1961.0, 4: 2538.0}

# Volumenstrom-Referenzwerte (Q_ref m³/h, RPM_ref) pro Modell
# Bezugsquelle: Herstellerdatenblatt Fränkische Rohrwerke, Bezugs-Volumenstrom @ 50 Pa
VOLUMENSTROM_REF: dict[str, tuple[float, float]] = {
    MODEL_PROFI_AIR_400: (280.0, 2085.0),  # BP4 5.4V; RPM aus Messdaten interpoliert
    MODEL_PROFI_AIR_250: (175.0, 1961.0),  # BP4 5.1V
}

# Statische Fallback-Volumenstromtabelle (ohne RPM-Daten)
VOLUMENSTROM_STATIC: dict[str, dict[int, int]] = {
    MODEL_PROFI_AIR_400: {1: 115, 2: 169, 3: 263, 4: 341},
    MODEL_PROFI_AIR_250: {1:  77, 2: 112, 3: 175, 4: 226},
}

# Nennleistung pro Lüftungsstufe in Watt (gemessen)
LEVEL_TO_WATT: dict[int, float] = {
    1: 11.0,
    2: 17.5,
    3: 43.5,
    4: 80.0,
}

# Config Entry Keys fuer Watt-Werte
CONF_WATT_LEVEL_1 = "watt_level_1"
CONF_WATT_LEVEL_2 = "watt_level_2"
CONF_WATT_LEVEL_3 = "watt_level_3"
CONF_WATT_LEVEL_4 = "watt_level_4"

# Standardwerte (Profi-Air 400 touch)
DEFAULT_WATT = WATT_DEFAULTS[MODEL_PROFI_AIR_400]

# Alle bekannten XML-Tags aus status.xml
# Wird fuer unknown_tags Discovery genutzt
ALL_KNOWN_TAGS: frozenset[str] = frozenset({
    # Temperaturen
    "abl0", "zul0", "aul0", "fol0",
    # Motor RPM
    "MoStZlUm", "MoStAlUm",
    # Motor Spannung
    "MoStZlVo", "MoStAlVo",
    # Airflow Volt pro Stufe
    "st1z", "st1a", "st2z", "st2a",
    "st3z", "st3a", "st4z", "st4a",
    # Betriebsstunden
    "BsSt1", "BsSt2", "BsSt3", "BsSt4",
    "BsFs", "BsVhr",
    # Temperaturkorrekturen
    "kor1", "kor2", "kor3", "kor4",
    # Status / Steuerung
    "safety", "passiv", "vorheiz", "installtyp",
    "filter0", "filtertime", "rest_time",
    "sensortyp1", "sensortyp2", "sensortyp3", "sensortyp4",
    "S1amb0", "S2amb0", "S3amb0", "S4amb0",
    "meldung", "grundst", "nachlauf",
    "config_mac", "config_ip",
    "bypass", "partytime", "aktuell0", "control0",
    "BipaAutAUL", "BipaAutABL",
    "stufe1", "stufe2", "stufe3", "stufe4",
    "SprachWahl",
    # Digital inputs (firmware update)
    "DiIn1", "DiIn2", "DiIn3",
    # Passive heat recovery thresholds
    "PassivHE", "PassivHA",
    # Status (firmware update)
    "sensor0", "soze", "time", "date", "events",
})

# Dynamically generated tags -- scheduler and UI strings
ALL_KNOWN_TAGS = ALL_KNOWN_TAGS | frozenset(
    [f"prg{i}" for i in range(1, 11)]
    + [f"prg_start{i}" for i in range(1, 11)]
    + [f"prg_stop{i}" for i in range(1, 11)]
    + [f"prg_wota{i}" for i in range(1, 11)]
    + [f"langtxt{i}" for i in range(0, 155)]
)

# Bekannte Endpunkte
ENDPOINT_INSTALL = "/install/install.htm"
ENDPOINT_TIME    = "/time.htm"
ENDPOINT_WOPLA   = "/wopla.htm"
ENDPOINT_SETUP   = "/setup.htm"
ENDPOINT_STATUS  = "/status.xml"

# Options Flow -- konfigurierbare Parameter
CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 30  # Sekunden
MIN_SCAN_INTERVAL = 30
MAX_SCAN_INTERVAL = 300  # 5 Minuten

# Pflicht-Tags die in jeder gueltigen status.xml-Antwort vorhanden sein muessen
REQUIRED_XML_TAGS: frozenset[str] = frozenset({
    "abl0", "zul0", "aul0", "stufe1",
})

# ── Modbus (Flex / Flat) ───────────────────────────────────────────────────────

DEFAULT_MODBUS_PORT = 502

# Alarm-Codes Register 40517 → Klartext (E1–E15)
# Quelle: Fränkische Betriebsanleitung profi-air 250/360 flex, Abschnitt Störungsmeldungen
FLEX_ALARM_TEXT: dict[int, str] = {
    0:  "",
    1:  "E1 – Abluftventilator",
    2:  "E2 – Zuluftventilator",
    3:  "E3 – Sommerbypass",
    4:  "E4 – Außenluftfühler T1",
    5:  "E5 – Zuluftfühler T2",
    6:  "E6 – Abluftfühler T3",
    7:  "E7 – Fortluftfühler T4",
    8:  "E8 – Raumluftfühler",
    9:  "E9 – Interner Abluftfühler",
    10: "E10 – Außenluft < –13 °C",
    11: "E11 – Zuluft < 5 °C (Frostgefahr)",
    12: "E12 – Feuerschutz > 70 °C",
    13: "E13 – Kommunikationsstörung",
    14: "E14 – Brandschutz ausgelöst",
    15: "E15 – Hoher Kondensatwasserstand",
}

# Betriebsmodi Register 40473 (lesen) → Anzeige-Text
FLEX_MODE_TEXT: dict[int, str] = {
    1:  "Manuell",
    2:  "Bedarfsgesteuert",
    3:  "Wochenprogramm",
    5:  "Urlaub",
    6:  "Sommer",
    7:  "Nacht",
    12: "Kaminbetrieb",
}

# Anzeige-Text → Bitmask für Register 40169 (schreiben)
# Quelle: UVC Controller Doku — "Start"-Bitmask für jeden Modus
FLEX_MODE_TO_WRITE: dict[str, int] = {
    "Manuell":          0x0004,
    "Bedarfsgesteuert": 0x0002,
    "Wochenprogramm":   0x0008,
    "Urlaub":           0x0010,
    "Sommer":           0x0800,
    "Nacht":            0x0020,
    "Kaminbetrieb":     0x0040,
}

# "End"-Bitmask zum expliziten Beenden spezieller Modi (0x8000 | Start-Bitmask)
# Wird genutzt wenn Modus-Wechsel ein explizites Ende des Vorgänger-Modus erfordert
FLEX_MODE_TO_END: dict[str, int] = {
    "Urlaub":       0x8010,
    "Sommer":       0x8800,
    "Nacht":        0x8020,
    "Kaminbetrieb": 0x8040,
    "Bypass":       0x8080,  # Manueller Bypass Ende
}

# Lüftungsstufen-Verhältnisse (aus Betriebsanleitung profi-air 250/360 flex)
# Stufe 3 = 100 % (Nennvolumenstrom, commissioning-abhängig)
# Wird für Volumenstrom-Schätzung genutzt wenn kein VOLUMENSTROM_REF verfügbar.
FLEX_LEVEL_RATIO: dict[int, float] = {
    1: 0.49,
    2: 0.70,
    3: 1.00,
    4: 1.00,  # Stufe 4 = Maximum; kein festes Verhältnis zu Stufe 3
}
