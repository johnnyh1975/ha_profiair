# Modbus TCP Registermap — profi-air flex / flat

Technische Referenz für die Entwicklung der `KWLFlexCoordinator`-Implementierung.  
Quelle: *Fränkische UVC Controller – Modbus TCP/IP*, Revision 3.b, 2020-07-07.

---

## Protokoll

| Parameter | Wert |
|---|---|
| Transport | TCP |
| Port | 502 (Standard) |
| Unterstützte Function Codes | FC03 (Read Holding Registers), FC16 (Write Multiple Registers) |
| Gleichzeitige Verbindungen | max. 3 |
| Inaktivitäts-Timeout | 60 Sekunden |
| Register-Dimension | 32 Bit (je 2 × 16-Bit-Register, Low-Adresse zuerst) |
| Float-Byte-Order | **CDAB** → `word_order='little'` in pymodbus |
| Integer-Byte-Order | Low-Register zuerst → `word_order='little'` in pymodbus |
| Adressierung | 1-basiert (40001 = offset 0 im FC03-Request) |

### pymodbus-Dekodierung (v3.x)

```python
from pymodbus.client.mixin import ModbusClientMixin

# Float CDAB (alle Temperatur- und RPM-Werte)
value = ModbusClientMixin.convert_from_registers(
    registers,                        # [low_reg, high_reg]
    ModbusClientMixin.DATATYPE.FLOAT32,
    word_order='little'
)

# UINT32 Low-first (alle Integer-Werte)
value = ModbusClientMixin.convert_from_registers(
    registers,
    ModbusClientMixin.DATATYPE.UINT32,
    word_order='little'
)

# Write UINT32
regs = ModbusClientMixin.convert_to_registers(
    value,
    ModbusClientMixin.DATATYPE.UINT32,
    word_order='little'
)
await client.write_registers(address=offset, values=regs, device_id=1)
```

---

## Gerätetypen (prmSystemID, Register 40003, Byte 0)

| Unit-Typ-Code | Modell | Integration |
|---|---|---|
| 4 | profi-air 180 flat | ⚠️ Experimentell |
| 11 | profi-air 250 flex | ✅ |
| 15 | profi-air 360 flex | ✅ |

---

## Vollständige Registermap

### System / Identität

| Register | Offset | Name | Typ | R/W | Integration | Verwendung |
|---|---|---|---|---|---|---|
| 40003 | 2 | `prmSystemID` | UINT32 | R | ✅ | Byte 0: Unit-Typ; Bits: Capabilities |
| 40005 | 4 | `prmSystemSerialNumLow` | UINT32 | R | — | Seriennummer [low] |
| 40007 | 6 | `prmSystemSerialNumHigh` | UINT32 | R | — | Seriennummer [high] |
| 40009–40024 | 8–23 | `prmSystemName1–8` | UINT32 | W | — | Gerätename ASCII (8 × 32 Bit = 32 Zeichen) |
| 40025 | 24 | `prmFWVersion` | UINT32 | R | ✅ | Firmware Major (Byte 1), Minor (Byte 0) → Device Info |
| 40041 | 40 | `prmMACAddrHigh` | UINT32 | R | ✅ | MAC-Adresse [high] → Unique ID |
| 40043 | 42 | `prmMACAddrLow` | UINT32 | R | ✅ | MAC-Adresse [low] → Unique ID |
| 40611 | 610 | `prmSystemIDComponents` | UINT32 | R | — | Detaillierte Komponenten-Bitmaske |
| 40669 | 668 | `prmStartExploitationDateStamp` | UINT32 | R | — | Installationsdatum (Unix) |

### Netzwerk (nicht verwendet)

| Register | Offset | Name | Typ | R/W | Integration |
|---|---|---|---|---|---|
| 40027 | 26 | `prmDHCPEN` | UINT32 | R | — |
| 40029 | 28 | `prmCurrentIPAddress` | UINT32 | R | — |
| 40033 | 32 | `prmCurrentIPMask` | UINT32 | R | — |
| 40037 | 36 | `prmCurrentIPGateway` | UINT32 | R | — |

### Datum / Zeit

| Register | Offset | Name | Typ | R/W | Integration | Verwendung |
|---|---|---|---|---|---|---|
| 40109 | 108 | `prmDateTime` | UINT32 | R | — | Aktuelle Uhrzeit als Unix-Timestamp |
| 40111 | 110 | `prmDateTimeSet` | UINT32 | W | ✅ | Zeitsync: Unix-Timestamp schreiben |
| 40625 | 624 | `prmWorkTime` | UINT32 | R | ✅ | Gesamt-Betriebsstunden |

### Hardware / Installation

| Register | Offset | Name | Typ | R/W | Integration | Verwendung |
|---|---|---|---|---|---|---|
| 40085 | 84 | `prmHALLeft` | UINT32 | R | ✅ | 1 = Schalter in Position B (Left) |
| 40087 | 86 | `prmHALRight` | UINT32 | R | ✅ | 1 = Schalter in Position A (Right) |

**A/B-Schalterlogik:** Bestimmt welcher Fan Abluft vs. Zuluft ist.
- `HALLeft=0, HALRight=1` → Schalter in A → Fan1 = Außenluft/Zuluft, Fan2 = Abluft/Fortluft
- `HALLeft=1, HALRight=0` → Schalter in B → umgekehrte Zuordnung
- Einmalig beim Setup lesen und cachen (`KWLFlexCapabilities`).

### Lüfter / Motoren

| Register | Offset | Name | Typ | R/W | Integration | Verwendung |
|---|---|---|---|---|---|---|
| 40101 | 100 | `prmHALTaho1` | FLOAT | R | ✅ | Fan1 RPM (je nach A/B: Ab- oder Zuluft) |
| 40103 | 102 | `prmHALTaho2` | FLOAT | R | ✅ | Fan2 RPM |
| 40325 | 324 | `prmRomIdxSpeedLevel` | UINT32 | R/W | ✅ | Lüftungsstufe 0–4; Write nur in Manual-Mode |
| 40519 | 518 | `prmRefValEx` | UINT32 | R | ✅ | Referenz-RPM Abluft bei Stufe 3 (Inbetriebnahme) |
| 40521 | 520 | `prmRefValSupl` | UINT32 | R | ✅ | Referenz-RPM Zuluft bei Stufe 3 |

**Fan-Level schreiben:** Nur in Manual-Mode (Mode-Code 4). Vorher prüfen ob Gerät in Manual-Mode ist; falls nicht: zuerst Mode auf Manual setzen (0x0004 → Register 40169), dann Level schreiben.
Torsten600 meldet: FC16 mit Block ab Offset 324 nötig (FC06 funktioniert nicht). **Genaues Block-Format ausstehend.**

### Temperaturen

| Register | Offset | Name | Typ | R/W | Integration | Verwendung |
|---|---|---|---|---|---|---|
| 40133 | 132 | `prmRamIdxT1` | FLOAT | R | ✅ | T1 Außenluft (°C) |
| 40135 | 134 | `prmRamIdxT2` | FLOAT | R | ✅ | T2 Zuluft (°C) |
| 40137 | 136 | `prmRamIdxT3` | FLOAT | R | ✅ | T3 Abluft/Extract (°C) |
| 40139 | 138 | `prmRamIdxT4` | FLOAT | R | ✅ | T4 Fortluft/Exhaust (°C) |
| 40141 | 140 | `prmRamIdxT5` | FLOAT | R | ✅ | T5 Raumtemperatur Funkfernbedienung (°C); 0 wenn nicht verbaut |

### Betrieb / Modi

| Register | Offset | Name | Typ | R/W | Integration | Verwendung |
|---|---|---|---|---|---|---|
| 40169 | 168 | `prmRamIdxUnitMode` | UINT32 | W | ✅ | Modus setzen (Bitmaske, siehe Tabelle unten) |
| 40473 | 472 | `prmCurrentBLState` | UINT32 | R | ✅ | Aktueller Modus (Integer, siehe Tabelle unten) |

**Modus-Codes für 40473 (Read):**

| Wert | Bedeutung |
|---|---|
| 1 | Manuell |
| 2 | Bedarfsgesteuert (Demand / Auto) |
| 3 | Wochenprogramm |
| 5 | Urlaub (Away) |
| 6 | Sommer |
| 7 | Nacht |
| 12 | Kaminbetrieb (Fireplace) |

**Modus-Bitmasken für 40169 (Write):**

| Hex | Dezimal | Aktion |
|---|---|---|
| 0x0002 | 2 | Bedarfsgesteuert aktivieren |
| 0x0004 | 4 | Manuell aktivieren |
| 0x0008 | 8 | Wochenprogramm aktivieren |
| 0x0010 | 16 | Urlaub starten |
| 0x8010 | 32784 | Urlaub beenden |
| 0x0020 | 32 | Nacht aktivieren |
| 0x8020 | 32800 | Nacht deaktivieren |
| 0x0040 | 64 | Kaminbetrieb starten |
| 0x8040 | 32832 | Kaminbetrieb beenden |
| 0x0080 | 128 | Bypass manuell öffnen |
| 0x8080 | 32896 | Bypass manuell schließen |
| 0x0800 | 2048 | Sommer aktivieren |
| 0x8800 | 34816 | Sommer deaktivieren |

### Bypass

| Register | Offset | Name | Typ | R/W | Integration | Verwendung |
|---|---|---|---|---|---|---|
| 40199 | 198 | `prmRamIdxBypassActualState` | UINT32 | R | ✅ | Bypass-Status (0=zu, 1=Bewegung, 32=schließt, 64=öffnet, 255=offen) |
| 40265 | 264 | `prmRamIdxBypassManualTimeout` | UINT32 | R | — | Manueller Bypass Timeout (60–480 Min) |
| 40445 | 444 | `prmBypassTmin` | FLOAT | R | ✅ | Min. Außenlufttemp. für Bypass-Öffnung (°C) |
| 40447 | 446 | `prmBypassTmax` | FLOAT | R | ✅ | Max. Ablufttemp. für Bypass-Öffnung (°C) |
| 40541 | 540 | `prmFireplacePreset` | UINT32 | R | — | 1 = Kaminbetrieb-Hardware verbaut |

### Sensoren (optional)

| Register | Offset | Name | Typ | R/W | Integration | Verwendung |
|---|---|---|---|---|---|---|
| 40197 | 196 | `prmRamIdxRh3Corrected` | UINT32 | R | ✅ | Luftfeuchte % (0 wenn kein Sensor) |
| 40341 | 340 | `prmRomIdxRhSetPoint` | UINT32 | R | ✅ | RH-Sollwert % für Bedarfssteuerung (35–65) |
| 40431 | 430 | `prmVOC` | UINT32 | R | ✅ | VOC ppm (0 wenn kein Sensor) |
| 40575 | 574 | `prmHACCO2Val` | UINT32 | R | ✅ | CO2 ppm via HAC-Modul (0 wenn nicht verbaut) |

**VOC-Schwellen (Write, nicht implementiert):**

| Register | Offset | Name | Schwelle |
|---|---|---|---|
| 40563 | 562 | `prmPPM1Unit` | VOC Low (Stufe 1→2) |
| 40565 | 564 | `prmPPM2Unit` | VOC Mid (Stufe 2→3) |
| 40567 | 566 | `prmPPM3Unit` | VOC High (Stufe 3→4) |
| 40569 | 568 | `prmPPM1External` | CO2 Low |
| 40571 | 570 | `prmPPM2External` | CO2 Mid |
| 40573 | 572 | `prmPPM3External` | CO2 High |

### Vorheizer

| Register | Offset | Name | Typ | R/W | Integration | Verwendung |
|---|---|---|---|---|---|---|
| 40161 | 160 | `prmPreheaterDutyCycle` | UINT32 | R | ✅ | Duty-Cycle % (0 = aus) |
| 40193 | 192 | `prmRamIdxHac1FirmwareVersion` | UINT32 | R | — | HAC1 Firmware-Version |
| 40245 | 244 | `prmRamIdxHac1Components` | UINT32 | R | — | HAC1 Komponenten-Flags |

**HAC Afterheater Setpoints (nicht implementiert):**

| Register | Offset | Name |
|---|---|---|
| 40345 | 344 | `prmRomIdxAfterHeaterT2SetPoint` |
| 40347 | 346 | `prmRomIdxAfterHeaterT3SetPoint` |
| 40349 | 348 | `prmRomIdxAfterHeaterT5SetPoint` |

### Filter

| Register | Offset | Name | Typ | R/W | Integration | Verwendung |
|---|---|---|---|---|---|---|
| 40555 | 554 | `prmFilterRemainingTime` | UINT32 | R | ✅ | Restlaufzeit Filter (Tage, 0–360) |
| 40557 | 556 | `prmFilterDefaultTime` | UINT32 | R/W | ✅ | Filterintervall (Tage, 0–360) — Number-Entity |
| 40559 | 558 | `prmFilterReset` | UINT32 | W | ✅ | 1 schreiben = Timer zurücksetzen |

### Alarme

| Register | Offset | Name | Typ | R/W | Integration | Verwendung |
|---|---|---|---|---|---|---|
| 40515 | 514 | `prmSetAlarmNum` | UINT32 | W | ✅ | 0 schreiben = aktiven Alarm löschen |
| 40517 | 516 | `prmLastActiveAlarm` | UINT32 | R | ✅ | Aktiver Alarm-Code (0 = kein Alarm) |

**Alarm-Code-Tabelle (40517):**

| Code | Gerätecode | Bedeutung | Geräteverhalten |
|---|---|---|---|
| 0 | — | Kein Alarm | — |
| 1 | E1 | Abluftventilator | Gerät stoppt komplett |
| 2 | E2 | Zuluftventilator | Gerät stoppt komplett |
| 3 | E3 | Sommerbypass-Klappe verklemmt | Bypass bleibt in letzter Stellung |
| 4 | E4 | Außenluftfühler T1 defekt | Fail-safe Mode 1 (kein Bypass) |
| 5 | E5 | Zuluftfühler T2 defekt | Fail-safe Mode 1 |
| 6 | E6 | Abluftfühler T3 defekt | Fail-safe Mode 2 (sehr niedrige Drehzahl) |
| 7 | E7 | Fortluftfühler T4 defekt | Fail-safe Mode 2 |
| 8 | E8 | Raumluftfühler (Fernbedienung) defekt | Weiterbetrieb ohne Raumtemp. |
| 9 | E9 | Interner Abluftfühler (Feuchte/VOC) defekt | Fail-safe Mode 2 |
| 10 | E10 | Außenluft < –13 °C | Frostschutzmodus aktiv |
| 11 | E11 | Zuluft < 5 °C (Frostgefahr) | Gerät stoppt komplett |
| 12 | E12 | Feuerschutzfühler > 70 °C | Gerät stoppt komplett |
| 13 | E13 | Kommunikationsstörung | Gerät außer Betrieb |
| 14 | E14 | Brandschutz-Digitaleingang ausgelöst | Gerät stoppt, nur manuell rücksetzbar |
| 15 | E15 | Hoher Kondensatwasserstand | Gerät stoppt komplett |

### Nachtmodus-Konfiguration (nicht implementiert)

| Register | Offset | Name | Typ | R/W |
|---|---|---|---|---|
| 40333 | 332 | `prmRomIdxNightModeStartHour` | UINT32 | W |
| 40335 | 334 | `prmRomIdxNightModeStartMin` | UINT32 | W |
| 40337 | 336 | `prmRomIdxNightModeEndHour` | UINT32 | W |
| 40339 | 338 | `prmRomIdxNightModeEndMin` | UINT32 | W |

### Wochenprogramm (nicht implementiert)

| Register | Offset | Name | Typ | R/W |
|---|---|---|---|---|
| 40467 | 466 | `prmNumOfWeekProgram` | UINT32 | W |
| 40627–... | 626–... | Wochenprogramm-Datenblock | UINT32 | R/W |

Struktur: 21 Register pro Tag × 7 Tage = 147 Register minimum. Format komplex, nicht dokumentiert.

---

## Batch-Read-Strategie (KWLFlexCoordinator)

Minimale Roundtrips durch zusammenhängende Register-Blöcke:

```
Block 1: 40085–40088   (4 Register)  → A/B-Switch, einmalig beim Setup
Block 2: 40101–40104   (4 Register)  → Fan RPMs
Block 3: 40133–40142   (10 Register) → T1–T5 (5 Floats × 2)
Block 4: 40161–40162   (2 Register)  → Preheater
Block 5: 40197–40200   (4 Register)  → RH + Bypass State
Block 6: 40325–40326   (2 Register)  → Fan Level
Block 7: 40341–40342   (2 Register)  → RH Setpoint
Block 8: 40431–40432   (2 Register)  → VOC
Block 9: 40445–40448   (4 Register)  → Bypass Tmin + Tmax
Block 10: 40473–40474  (2 Register)  → Current Mode
Block 11: 40515–40522  (8 Register)  → Alarm Clear + Alarm Code + Ref RPMs
Block 12: 40555–40560  (6 Register)  → Filter Remaining + Default + Reset
Block 13: 40575–40576  (2 Register)  → CO2
Block 14: 40625–40626  (2 Register)  → Work Time
```

In der Praxis: zusammenhängende Blöcke zusammenfassen wo sinnvoll, um FC03-Requests zu minimieren. Der Coordinator liest alles in einem Poll-Zyklus.

---

## Lüftungsstufen-Verhältnisse (aus Betriebsanleitung)

| Stufe | Funktion | Volumenstrom |
|---|---|---|
| 0 | Aus | 0 % |
| 1 | Feuchteschutz | 49 % von Stufe 3 |
| 2 | Reduziert | 70 % von Stufe 3 |
| 3 | Nennlüftung | 100 % (Nenn-Volumenstrom, commissioning-abhängig) |
| 4 | Intensivlüftung | Maximum; auto-Rückkehr zu Stufe 3 nach 4 Stunden |

Referenz-RPM bei Stufe 3 direkt aus Gerät: Register 40519 (Abluft) und 40521 (Zuluft).  
Wird bei Commissioning via cockpit pro gesetzt. Ableitbare Werte für Stufen 1/2 via 49%/70%-Verhältnis.

---

## Offene Fragen (Stand: Planung v2.0.0)

| # | Frage | Status |
|---|---|---|
| 1 | FC16-Block-Format für Fan-Level-Write: welche Register, welche Werte für Register 2–10? | ⏳ Torsten600 |
| 2 | Watt-Messwerte Stufe 1–4 für 250 flex und 360 flex (Klammermessung) | ⏳ Torsten600 |
| 3 | A/B-Schalterstellung auf Torsten600s Gerät (Register 40085/40087) | ⏳ Torsten600 |
