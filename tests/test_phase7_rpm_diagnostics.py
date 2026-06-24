"""Tests fuer RPM-basierte Diagnostik in KWLAnalytics: rpm_anomaly und
filter_clogging_suspected.

Hintergrund (gefunden 23. Juni 2026, im Rahmen der Auswertung eines
Community-Beitrags von Torsten600 zu RPM-Drift als Filterindikator):

1. BUGFIX: rpm_anomaly und (neu) filter_clogging_suspected dokumentierten
   eine Mindest-Stichprobengroesse (MIN_N_RPM=500) vor der ersten Warnung,
   pruefften diese aber nirgends im Code -- WelfordEMA.z_score() liefert
   bereits ab n=2 einen Wert. Auf einer frischen Installation konnten beide
   Properties dadurch voreilig (und potenziell falsch) feuern.

2. NEU: filter_clogging_suspected ergaenzt rpm_anomaly um die fehlende
   Richtung. rpm_anomaly erkennt nur RPM UNTER der Baseline (Motor-
   /Lagerverschleiss). Zunehmender Filterwiderstand zwingt den EC-Motor bei
   gleicher Stufe zu HOEHERER Drehzahl, um den Volumenstrom zu halten --
   ohne diese Ergaenzung waere dieses Phaenomen fuer Touch- und Flex-Geraete
   unsichtbar geblieben, obwohl die Baseline-Infrastruktur (Welford-EMA pro
   Stufe+Saison) dafuer bereits vollstaendig vorhanden war.

Beide Properties nutzen exakt dieselbe selbstkalibrierende Baseline -- im
Gegensatz zum flex-spezifischen filter_rpm_drift_pct (fester Inbetriebnahme-
Referenzwert, nur fuer Stufe 3), funktioniert dieser Mechanismus protokoll-
unabhaengig fuer Touch- und Flex-Geraete gleich.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(
    0, str(Path(__file__).parent.parent / "custom_components" / "kwl_fraenkische")
)
from analytics import KWLAnalytics, KWLPollSnapshot, MIN_N_RPM  # noqa: E402


def _drive_baseline(
    analytics: KWLAnalytics,
    level: int,
    rpm: float,
    n: int,
    start_ts: float = 1_750_000_000.0,
    poll_interval_s: float = 30.0,
) -> float:
    """Speist n Polls mit konstanter RPM in die Stufe+Saison-Baseline ein.

    Gibt den Zeitstempel des letzten Polls zurueck, fuer Folge-Updates.
    Nutzt eine moderate Sommertemperatur, damit die Saison eindeutig ist.
    """
    ts = start_ts
    for _ in range(n):
        snap = KWLPollSnapshot(
            timestamp=ts,
            temp_abluft=23.0, temp_aussenluft=22.0,  # Sommer, knapp über Schwelle
            rpm_abluft=rpm, rpm_zuluft=rpm * 1.2,
            current_level=level,
        )
        analytics.update(snap, poll_interval_s=poll_interval_s)
        ts += poll_interval_s
    return ts


class TestRpmAnomalyBugfixSuppression:
    """Regressionstest fuer den MIN_N_RPM-Bug: Baseline mit wenigen Samples
    darf KEINE Warnung ausloesen, selbst bei extremer Abweichung."""

    def test_rpm_anomaly_suppressed_with_few_samples(self):
        analytics = KWLAnalytics()
        # Nur 10 Polls bei 1000 RPM etablieren eine instabile/unfertige Baseline
        ts = _drive_baseline(analytics, level=2, rpm=1000.0, n=10)

        # Extremer Ausreisser nach unten -- WUERDE ohne Fix sofort feuern,
        # da z_score() schon ab n=2 einen Wert liefert.
        snap = KWLPollSnapshot(
            timestamp=ts, temp_abluft=23.0, temp_aussenluft=22.0,
            rpm_abluft=200.0, rpm_zuluft=240.0, current_level=2,
        )
        analytics.update(snap, poll_interval_s=30.0)

        assert analytics.rpm_anomaly is False, (
            "Bug-Regression: rpm_anomaly darf vor MIN_N_RPM Samples "
            "nicht feuern, unabhaengig von der Abweichungsgroesse"
        )

    def test_filter_clogging_suspected_suppressed_with_few_samples(self):
        analytics = KWLAnalytics()
        ts = _drive_baseline(analytics, level=2, rpm=1000.0, n=10)

        # Extremer Ausreisser nach oben
        snap = KWLPollSnapshot(
            timestamp=ts, temp_abluft=23.0, temp_aussenluft=22.0,
            rpm_abluft=5000.0, rpm_zuluft=6000.0, current_level=2,
        )
        analytics.update(snap, poll_interval_s=30.0)

        assert analytics.filter_clogging_suspected is False, (
            "filter_clogging_suspected darf vor MIN_N_RPM Samples "
            "nicht feuern, unabhaengig von der Abweichungsgroesse"
        )

    def test_min_n_rpm_is_500(self):
        """Stellt sicher dass der Schwellenwert nicht versehentlich verändert wurde."""
        assert MIN_N_RPM == 500


class TestRpmAnomalyEstablishedBaseline:
    """Mit etablierter Baseline (>= MIN_N_RPM) muss rpm_anomaly korrekt
    auf signifikant NIEDRIGE RPM reagieren (Motor-/Lagerverschleiss)."""

    def test_fires_on_sustained_low_rpm(self):
        analytics = KWLAnalytics()
        # Stabile Baseline um 1000 RPM mit etwas natürlicher Varianz
        ts = 1_750_000_000.0
        import random
        random.seed(42)
        for _ in range(MIN_N_RPM + 10):
            rpm = 1000.0 + random.uniform(-5, 5)
            snap = KWLPollSnapshot(
                timestamp=ts, temp_abluft=23.0, temp_aussenluft=22.0,
                rpm_abluft=rpm, rpm_zuluft=rpm * 1.2, current_level=2,
            )
            analytics.update(snap, poll_interval_s=30.0)
            ts += 30.0

        # Deutlicher Abfall -- weit ausserhalb der engen Varianz
        snap = KWLPollSnapshot(
            timestamp=ts, temp_abluft=23.0, temp_aussenluft=22.0,
            rpm_abluft=850.0, rpm_zuluft=1020.0, current_level=2,
        )
        analytics.update(snap, poll_interval_s=30.0)

        assert analytics.rpm_anomaly is True
        assert analytics.filter_clogging_suspected is False, (
            "Bei niedriger RPM darf die entgegengesetzte Diagnose nicht "
            "gleichzeitig feuern"
        )

    def test_does_not_fire_on_normal_variance(self):
        analytics = KWLAnalytics()
        ts = 1_750_000_000.0
        import random
        random.seed(7)
        for _ in range(MIN_N_RPM + 10):
            rpm = 1000.0 + random.uniform(-5, 5)
            snap = KWLPollSnapshot(
                timestamp=ts, temp_abluft=23.0, temp_aussenluft=22.0,
                rpm_abluft=rpm, rpm_zuluft=rpm * 1.2, current_level=2,
            )
            analytics.update(snap, poll_interval_s=30.0)
            ts += 30.0

        # Innerhalb der normalen Schwankung
        snap = KWLPollSnapshot(
            timestamp=ts, temp_abluft=23.0, temp_aussenluft=22.0,
            rpm_abluft=1002.0, rpm_zuluft=1202.0, current_level=2,
        )
        analytics.update(snap, poll_interval_s=30.0)

        assert analytics.rpm_anomaly is False
        assert analytics.filter_clogging_suspected is False


class TestFilterCloggingSuspected:
    """Neue Diagnose: signifikant HOHE RPM bei gleicher Stufe+Saison-Baseline
    deutet auf zunehmenden Filterwiderstand hin (Community-Beitrag Torsten600)."""

    def test_fires_on_sustained_high_rpm(self):
        analytics = KWLAnalytics()
        ts = 1_750_000_000.0
        import random
        random.seed(99)
        for _ in range(MIN_N_RPM + 10):
            rpm = 1000.0 + random.uniform(-5, 5)
            snap = KWLPollSnapshot(
                timestamp=ts, temp_abluft=23.0, temp_aussenluft=22.0,
                rpm_abluft=rpm, rpm_zuluft=rpm * 1.2, current_level=3,
            )
            analytics.update(snap, poll_interval_s=30.0)
            ts += 30.0

        # Deutlicher Anstieg -- Filter setzt dem Luftstrom mehr Widerstand entgegen
        snap = KWLPollSnapshot(
            timestamp=ts, temp_abluft=23.0, temp_aussenluft=22.0,
            rpm_abluft=1150.0, rpm_zuluft=1380.0, current_level=3,
        )
        analytics.update(snap, poll_interval_s=30.0)

        assert analytics.filter_clogging_suspected is True
        assert analytics.rpm_anomaly is False, (
            "Bei hoher RPM darf die entgegengesetzte Diagnose (Lagerverschleiss) "
            "nicht gleichzeitig feuern"
        )

    def test_works_identically_for_any_level(self):
        """Im Gegensatz zum flex-spezifischen filter_rpm_drift_pct (nur Stufe 3)
        funktioniert diese self-calibrating Diagnose fuer JEDE Stufe."""
        for level in (1, 2, 3, 4):
            analytics = KWLAnalytics()
            ts = 1_750_000_000.0
            import random
            random.seed(level)
            for _ in range(MIN_N_RPM + 10):
                rpm = 1000.0 + random.uniform(-5, 5)
                snap = KWLPollSnapshot(
                    timestamp=ts, temp_abluft=23.0, temp_aussenluft=22.0,
                    rpm_abluft=rpm, rpm_zuluft=rpm * 1.2, current_level=level,
                )
                analytics.update(snap, poll_interval_s=30.0)
                ts += 30.0

            snap = KWLPollSnapshot(
                timestamp=ts, temp_abluft=23.0, temp_aussenluft=22.0,
                rpm_abluft=1160.0, rpm_zuluft=1392.0, current_level=level,
            )
            analytics.update(snap, poll_interval_s=30.0)

            assert analytics.filter_clogging_suspected is True, (
                f"Diagnose muss auch bei Stufe {level} funktionieren"
            )
