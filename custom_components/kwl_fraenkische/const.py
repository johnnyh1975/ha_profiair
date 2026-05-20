"""Konstanten für die KWL Fränkische Rohrwerke Integration."""
DOMAIN = "kwl_fraenkische"

# Nennleistung pro Lueeftungsstufe in Watt (gemessen)
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
