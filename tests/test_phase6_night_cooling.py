"""Tests fuer KWLAnalytics / NightCoolingTracker (v2.0.1 Fix: Fenster-basierte
Nachtkuehlungsmessung statt Session-Erkennung).

Hintergrund-Bug (gefunden 23. Juni 2026):
Die KWL faellt nach ca. 2h Stufe-4-Betrieb intern auf eine niedrigere Stufe
zurueck. Die HA-Automation korrigiert dies binnen 1-11 Sekunden wieder auf
Stufe 4. Die alte session-basierte NightCoolingTracker-Logik schloss eine
Session bereits beim ERSTEN Poll der fan_at_level_4=False zeigte -- ein
30s-Poll-Intervall kann zufaellig in dieses kurze Korrekturfenster fallen
und zerreisst die Nacht dadurch in viele kleine Fragmente, von denen keines
die Mindestschwelle (0.5K) erreicht. Folge: night_cooling_last_k blieb
wochenlang "Unbekannt" trotz tatsaechlich wirksamer Nachtkuehlung.

Der Fix misst stattdessen im festen Fenster 22:00-07:00 Uhr direkt die
Netto-Temperaturdifferenz, unabhaengig von der Anzahl zwischenzeitlicher
kurzer Unterbrechungen.
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(
    0, str(Path(__file__).parent.parent / "custom_components" / "kwl_fraenkische")
)
from analytics import KWLAnalytics, KWLPollSnapshot, NightCoolingTracker  # noqa: E402


def _ts(year, month, day, hour, minute=0, second=0) -> float:
    """Baut einen lokalen Zeitstempel fuer Testzwecke (verwendet time.mktime,
    daher abhaengig von der lokalen Zeitzone des Testsystems -- ausreichend
    fuer diese Tests, da nur relative Stundenwerte ausgewertet werden)."""
    return time.mktime((year, month, day, hour, minute, second, 0, 0, -1))


def _recent_night_window(days_ago: int) -> tuple[float, float]:
    """Liefert (22:00-Start, 07:00-Ende) eines Nachtfensters, das `days_ago`
    Tage vor jetzt liegt.

    Wird für Tests von inactive_nights()/avg_active_minutes() benötigt, die
    relativ zu time.time() über ein 7-Tage-Fenster filtern -- feste
    Kalenderdaten würden brechen, sobald sie älter als 7 Tage sind.
    """
    now = time.localtime()
    base = time.mktime(
        (now.tm_year, now.tm_mon, now.tm_mday, 22, 0, 0, 0, 0, -1)
    ) - days_ago * 86400.0
    return base, base + 9 * 3600.0  # 22:00 → 07:00 nächster Tag


class TestNightCoolingWindowBasic:
    """Grundfunktion: ein durchgehendes Fenster mit klarem Delta wird erfasst."""

    def test_simple_full_night_no_interruption(self):
        tracker = NightCoolingTracker()
        poll_s = 1800.0  # grobe 30-Minuten-Schritte fuer kompakten Test

        # 22:00 Uhr: Fenster startet, T_abluft = 26.0°C
        t = _ts(2026, 6, 22, 22, 0)
        tracker.update(True, 26.0, 20.0, True, t, poll_s)

        # Stufe 4 laeuft durchgehend bis 06:00, T_abluft faellt linear auf 23.5°C
        temps = [25.6, 25.2, 24.8, 24.4, 24.0, 23.7, 23.5, 23.5]
        for i, temp in enumerate(temps, start=1):
            t += poll_s
            tracker.update(True, temp, 20.0 - i * 0.2, True, t, poll_s)

        # 07:00 Uhr: Fenster endet (Stunde faellt aus dem Fenster), Fan nicht mehr auf 4
        t = _ts(2026, 6, 23, 7, 0)
        tracker.update(False, 23.5, 18.0, True, t, poll_s)

        assert tracker.last_event_k == pytest.approx(2.5, abs=0.01)
        assert tracker.last_active_minutes is not None
        assert tracker.last_active_minutes > 0
        assert tracker.last_efficiency_k_per_h is not None
        assert tracker.last_bypass_open_pct == pytest.approx(100.0, abs=0.1)

    def test_below_threshold_not_recorded(self):
        """Delta unter 0.5K darf keinen Eintrag erzeugen."""
        tracker = NightCoolingTracker()
        t = _ts(2026, 6, 22, 22, 0)
        tracker.update(True, 25.0, 22.0, True, t, 1800.0)
        t = _ts(2026, 6, 23, 7, 0)
        tracker.update(False, 24.8, 21.0, True, t, 1800.0)  # nur 0.2K Abfall

        assert tracker.last_event_k is None

    def test_no_level4_activity_never_recorded_as_event(self):
        """Kritischer Guard: faellt die Temperatur allein durch natuerliche
        Nachtabkuehlung (Stufe 4 nie gesetzt), darf das NICHT als
        Nachtkuehlungs-Erfolg gewertet werden -- unabhaengig vom Delta."""
        tracker = NightCoolingTracker()
        start, end = _recent_night_window(days_ago=1)
        t = start
        tracker.update(False, 26.0, 19.0, True, t, 1800.0)  # Stufe 4 NIE aktiv
        for _ in range(8):
            t += 1800.0
            tracker.update(False, 26.0 - 0.3, 19.0, True, t, 1800.0)
        tracker.update(False, 23.6, 17.0, True, end, 1800.0)  # 2.4K natuerlicher Abfall

        assert tracker.last_event_k is None, (
            "Eine Nacht ohne jede Stufe-4-Aktivitaet darf nicht als "
            "Kuehlerfolg gezaehlt werden, selbst bei deutlichem Temperaturabfall"
        )
        # Aber die Nacht muss als inaktive Nacht in den Summaries auftauchen
        assert tracker.inactive_nights(7.0) == 1

    def test_inactive_night_counted_separately_from_active_night(self):
        tracker = NightCoolingTracker()

        # Nacht 1: komplett inaktiv (vor 3 Tagen, innerhalb des 7-Tage-Fensters)
        start1, end1 = _recent_night_window(days_ago=3)
        tracker.update(False, 26.0, 19.0, True, start1, 1800.0)
        tracker.update(False, 24.0, 17.0, True, end1, 1800.0)

        # Nacht 2: aktiv mit klarem Erfolg (vor 2 Tagen)
        start2, end2 = _recent_night_window(days_ago=2)
        t = start2
        tracker.update(True, 26.0, 18.0, True, t, 1800.0)
        for _ in range(4):
            t += 1800.0
            tracker.update(True, 25.0, 18.0, True, t, 1800.0)
        tracker.update(False, 24.0, 17.0, True, end2, 1800.0)

        assert tracker.inactive_nights(7.0) == 1
        assert tracker.last_event_k is not None  # Nacht 2 zaehlt als Erfolg
        avg_active = tracker.avg_active_minutes(7.0)
        assert avg_active is not None
        assert 0 < avg_active < 150  # Mittelwert aus 0 und ~150 aktiven Minuten


class TestNightCoolingBugRegression:
    """Regressionstest fuer den urspruenglichen Fragmentierungs-Bug.

    Simuliert mehrfache kurze Geraete-Rueckfaelle (1-11 Sekunden) mitten in
    der Nacht, wie sie beim realen Geraet beobachtet wurden. Die Session darf
    dadurch NICHT fragmentiert werden -- das gesamte Fenster muss als ein
    durchgehender Erfolg erfasst werden.
    """

    def test_brief_device_reverts_do_not_fragment_session(self):
        tracker = NightCoolingTracker()
        poll_s = 30.0  # echtes Poll-Intervall

        t = _ts(2026, 6, 22, 23, 0)
        tracker.update(True, 27.0, 21.0, True, t, poll_s)

        # Simuliere 3 kurze Rueckfaelle die jeweils GENAU einen Poll treffen
        # (das ist der Mechanismus der den alten Bug ausgeloest hat)
        revert_points = [1800, 5400, 9000]  # nach 30/90/150 Minuten
        temp = 27.0
        elapsed = 0.0
        while elapsed < 7 * 3600:
            elapsed += poll_s
            t += poll_s
            temp -= 0.002  # langsame kontinuierliche Abkuehlung
            is_revert = any(abs(elapsed - rp) < poll_s for rp in revert_points)
            tracker.update(not is_revert, temp, 19.0, True, t, poll_s)

        # 07:00 Uhr: Fenster schliessen
        t = _ts(2026, 6, 23, 7, 0)
        tracker.update(False, temp, 18.0, True, t, poll_s)

        # Trotz 3 kurzer Unterbrechungen MUSS ein einziges Ereignis mit dem
        # vollen Nacht-Delta erfasst worden sein -- keine Fragmentierung.
        assert tracker.last_event_k is not None
        assert tracker.last_event_k > 0.5, (
            "Bug-Regression: kurze Geraete-Rueckfaelle haben die Session "
            "fragmentiert -- das volle Nacht-Delta wurde nicht erfasst"
        )


class TestNightCoolingCorrelationMetrics:
    """Stufe 2/3: Aktivitaets- und Bypass-Korrelation statt reinem Delta-K."""

    def test_low_efficiency_with_long_runtime_is_distinguishable(self):
        """Zwei Naechte mit gleichem Delta aber unterschiedlicher Laufzeit
        muessen unterschiedliche Effizienzwerte ergeben."""
        tracker_efficient = NightCoolingTracker()
        tracker_inefficient = NightCoolingTracker()

        # Effiziente Nacht: 2K Abfall in 2 aktiven Stunden
        t = _ts(2026, 6, 22, 22, 0)
        tracker_efficient.update(True, 26.0, 18.0, True, t, 1800.0)
        for _ in range(4):  # 4 × 30min = 2h
            t += 1800.0
            tracker_efficient.update(True, 25.5, 18.0, True, t, 1800.0)
        t = _ts(2026, 6, 23, 7, 0)
        tracker_efficient.update(False, 24.0, 18.0, True, t, 1800.0)

        # Ineffiziente Nacht: gleiches 2K Delta, aber 8 aktive Stunden
        t = _ts(2026, 6, 22, 22, 0)
        tracker_inefficient.update(True, 26.0, 18.0, True, t, 1800.0)
        for _ in range(16):  # 16 × 30min = 8h
            t += 1800.0
            tracker_inefficient.update(True, 25.8, 18.0, True, t, 1800.0)
        t = _ts(2026, 6, 23, 7, 0)
        tracker_inefficient.update(False, 24.0, 18.0, True, t, 1800.0)

        eff_value = tracker_efficient.last_efficiency_k_per_h
        ineff_value = tracker_inefficient.last_efficiency_k_per_h
        assert eff_value is not None and ineff_value is not None
        assert eff_value > ineff_value, (
            "Effizienzmetrik muss kurze, wirksame Naechte von langen, "
            "schwachen Naechten unterscheiden"
        )

    def test_bypass_closed_during_cooling_is_flagged_via_low_open_pct(self):
        """Wenn Stufe 4 laeuft aber der Bypass meist geschlossen ist, muss
        bypass_open_pct das aufdecken -- unabhaengig vom Delta-K-Ergebnis."""
        tracker = NightCoolingTracker()
        t = _ts(2026, 6, 22, 22, 0)
        tracker.update(True, 26.0, 18.0, False, t, 1800.0)  # Bypass zu
        for i in range(8):
            t += 1800.0
            bypass_open = (i == 7)  # nur im letzten Schritt offen
            tracker.update(True, 25.5 - i * 0.05, 18.0, bypass_open, t, 1800.0)
        t = _ts(2026, 6, 23, 7, 0)
        tracker.update(False, 25.0, 18.0, True, t, 1800.0)

        pct = tracker.last_bypass_open_pct
        assert pct is not None
        assert pct < 50.0, (
            "Bypass war waehrend der meisten aktiven Kuehlzeit geschlossen -- "
            "das muss sich in einem niedrigen bypass_open_pct zeigen"
        )

    def test_thermal_potential_reflects_actual_conditions(self):
        """avg_potential_k muss den durchschnittlichen Aussen-Innen-Unterschied
        waehrend der aktiven Kuehlzeit korrekt wiedergeben."""
        tracker = NightCoolingTracker()
        t = _ts(2026, 6, 22, 22, 0)
        tracker.update(True, 26.0, 21.0, True, t, 1800.0)  # Potenzial 5K
        for _ in range(4):
            t += 1800.0
            tracker.update(True, 25.5, 21.0, True, t, 1800.0)  # konstant 4.5K
        t = _ts(2026, 6, 23, 7, 0)
        tracker.update(False, 24.5, 21.0, True, t, 1800.0)

        potential = tracker.last_avg_potential_k
        assert potential is not None
        assert 4.0 < potential < 5.5


class TestNightCoolingSerialisation:
    """Persistenz muss alle neuen Felder inkl. laufendem Fensterzustand erhalten."""

    def test_round_trip_preserves_enriched_events(self):
        tracker = NightCoolingTracker()
        t = _ts(2026, 6, 22, 22, 0)
        tracker.update(True, 26.0, 19.0, True, t, 1800.0)
        for _ in range(4):
            t += 1800.0
            tracker.update(True, 25.0, 19.0, True, t, 1800.0)
        t = _ts(2026, 6, 23, 7, 0)
        tracker.update(False, 24.0, 19.0, True, t, 1800.0)

        d = tracker.to_dict()
        restored = NightCoolingTracker.from_dict(d)

        assert restored.last_event_k == tracker.last_event_k
        assert restored.last_efficiency_k_per_h == tracker.last_efficiency_k_per_h
        assert restored.last_bypass_open_pct == tracker.last_bypass_open_pct
        assert restored.last_avg_potential_k == tracker.last_avg_potential_k

    def test_legacy_tuple_events_still_load(self):
        """Alte v1.4.0-Speicherdaten (Tupel-Format) duerfen beim Laden nicht
        crashen -- sie werden als Minimal-Eintraege ohne Zusatzmetriken
        uebernommen."""
        legacy_dict = {
            "events": [[1750000000.0, 1.8], [1750100000.0, 2.1]],
            "window_active": False,
        }
        restored = NightCoolingTracker.from_dict(legacy_dict)
        assert restored.last_event_k == 2.1
        assert restored.last_active_minutes is None  # Altdaten haben das nicht

    def test_window_state_persists_across_restart(self):
        """Ein beim HA-Neustart noch offenes Fenster darf nicht verloren gehen --
        sonst wird die laufende Nacht beim Neuladen nicht korrekt abgeschlossen."""
        tracker = NightCoolingTracker()
        t = _ts(2026, 6, 22, 23, 30)
        tracker.update(True, 26.0, 19.0, True, t, 1800.0)

        d = tracker.to_dict()
        assert d["window_active"] is True
        assert d["start_temp"] == 26.0

        restored = NightCoolingTracker.from_dict(d)
        # Fenster fortsetzen und korrekt abschliessen
        t2 = _ts(2026, 6, 23, 7, 0)
        restored.update(False, 24.0, 18.0, True, t2, 1800.0)
        assert restored.last_event_k == pytest.approx(2.0, abs=0.01)


class TestKWLAnalyticsIntegration:
    """End-to-end durch KWLAnalytics.update() statt direkt am Tracker."""

    def test_full_night_via_poll_snapshots(self):
        analytics = KWLAnalytics()
        t = _ts(2026, 6, 22, 22, 0)

        snap = KWLPollSnapshot(
            timestamp=t, temp_abluft=26.0, temp_aussenluft=19.0,
            temp_zuluft=22.0, temp_fortluft=21.0,
            rpm_abluft=2538.0, rpm_zuluft=2865.0,
            current_level=4, bypass_status="Auto: Offen", fan_at_level_4=True,
        )
        analytics.update(snap, poll_interval_s=1800.0)

        for i in range(8):
            t += 1800.0
            snap = KWLPollSnapshot(
                timestamp=t, temp_abluft=26.0 - i * 0.3, temp_aussenluft=18.0,
                temp_zuluft=22.0, temp_fortluft=21.0,
                rpm_abluft=2538.0, rpm_zuluft=2865.0,
                current_level=4, bypass_status="Auto: Offen", fan_at_level_4=True,
            )
            analytics.update(snap, poll_interval_s=1800.0)

        t = _ts(2026, 6, 23, 7, 0)
        snap = KWLPollSnapshot(
            timestamp=t, temp_abluft=23.6, temp_aussenluft=17.0,
            temp_zuluft=21.0, temp_fortluft=20.0,
            rpm_abluft=900.0, rpm_zuluft=1050.0,
            current_level=1, bypass_status="Auto: Offen", fan_at_level_4=False,
        )
        analytics.update(snap, poll_interval_s=1800.0)

        assert analytics.night_cooling_last_k is not None
        assert analytics.night_cooling_last_k > 0.5
        assert analytics.night_cooling_last_efficiency_k_per_h is not None
        assert analytics.night_cooling_last_bypass_open_pct == pytest.approx(100.0, abs=0.1)
