"""Konstanten für die KWL Fränkische Rohrwerke Integration."""
DOMAIN = "kwl_fraenkische"

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

# Standardwerte (gemessen an Profi-Air 400)
DEFAULT_WATT = {1: 11.0, 2: 17.5, 3: 43.5, 4: 80.0}

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
