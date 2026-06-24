"""Self-calibrating analytics engine for KWL Fränkische Rohrwerke integration.

Pure Python -- zero Home Assistant imports.
The coordinator owns the Store; this module is storage-agnostic.
All baselines self-calibrate from observed device data using Welford's online
algorithm. Alerts are suppressed until the relevant baseline reaches its
minimum sample count so users never see false alarms on a fresh install.

Architecture
------------
KWLCoordinator
  ├── Store              (hass-facing, manages JSON persistence)
  └── KWLAnalytics       (pure Python, no HA dependencies)
        ├── WelfordEMA   (online mean+variance, O(1) space)
        ├── BypassTracker (episode durations + transition deque)
        └── NightCoolingTracker (T_abluft drop per activation)
"""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

# ── Storage ───────────────────────────────────────────────────────────────────

ANALYTICS_STORAGE_VERSION = 1
ANALYTICS_STORAGE_KEY_PREFIX = "kwl_fraenkische.analytics."

# ── Season discrimination ─────────────────────────────────────────────────────

SEASON_TEMP_THRESHOLD_C: float = 10.0
# T_aussenluft EMA alpha: 2/(N+1) with N = 2000 polls ≈ 16.7 h at 30 s
SEASON_EMA_ALPHA: float = 0.001

# ── Baseline sample requirements ──────────────────────────────────────────────

MIN_N_RPM: int = 500      # ≈ 4.2 h at 30 s → RPM baseline established
MIN_N_RATIO: int = 1000   # ≈ 8.3 h
MIN_N_HRE: int = 50       # 50 gated readings (η/ε slow to accumulate in summer)

# ── Alert thresholds ──────────────────────────────────────────────────────────

RPM_ALERT_SIGMA: float = 3.0    # z-score for RPM anomaly (low RPM → motor wear)
RATIO_ALERT_SIGMA: float = 3.0  # z-score for Zu/Ab ratio deviation
ETA_ALERT_DELTA: float = 0.08   # 8 pp sustained drop below seasonal baseline
# Community-Beitrag Torsten600 (Juni 2026, urspr. für flex-Referenz-RPM-Vergleich):
# zunehmender Filterwiderstand zwingt den EC-Motor bei gleicher Stufe zu HÖHERER
# Drehzahl, um den Volumenstrom zu halten -- die entgegengesetzte Richtung von
# rpm_anomaly (Lagerverschleiß = niedrigere RPM). Eigener Schwellenwert, da
# beide Phänomene unterschiedliche Ursachen und Handlungsempfehlungen haben.
RPM_HIGH_ALERT_SIGMA: float = 3.0

# ── Bypass episode tracking ───────────────────────────────────────────────────

MAX_BYPASS_EPISODES: int = 50
MAX_TRANSITIONS: int = 200
BYPASS_HUNT_WINDOW_S: float = 3600.0  # 60-minute window
BYPASS_HUNT_COUNT: int = 5            # transitions that trigger hunting alert
BYPASS_HUNT_EPISODE_MIN: float = 15.0 # avg open episode below this → hunting

# ── Night cooling ─────────────────────────────────────────────────────────────

MAX_NIGHT_EVENTS: int = 30
MAX_NIGHT_SUMMARIES: int = 30  # jedes abgeschlossene Fenster, auch ohne Kuehlerfolg
NIGHT_COOLING_MIN_DELTA_K: float = 0.5  # min net T_abluft drop to count as valid
NIGHT_WINDOW_START_HOUR: int = 22   # Fenster beginnt 22:00 Uhr (lokale Zeit)
NIGHT_WINDOW_END_HOUR: int = 7      # Fenster endet 07:00 Uhr (lokale Zeit)

# ── HRE gate conditions ───────────────────────────────────────────────────────

HRE_MIN_DELTA_K: float = 3.0          # supply-side η gate
HRE_WINTER_GATE_DELTA_K: float = 5.0  # winter baseline gate (bypass likely closed)
ENERGY_BALANCE_GATE_K: float = 8.0    # four-sensor balance gate (strict)


# ── Poll snapshot ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class KWLPollSnapshot:
    """Lightweight snapshot of a single coordinator poll for analytics."""

    timestamp: float                    # unix epoch seconds
    temp_abluft: float | None = None    # extract air (from rooms)
    temp_zuluft: float | None = None    # supply air (to rooms, after HRE)
    temp_aussenluft: float | None = None  # outdoor air
    temp_fortluft: float | None = None  # exhaust air (leaving building)
    rpm_abluft: float | None = None
    rpm_zuluft: float | None = None
    current_level: int | None = None    # 1-4
    bypass_status: str | None = None    # "Auto: Offen", "Auto: Zu", …
    # True when fan is at Stufe 4 — coordinator sets this; analytics uses it
    # to detect night cooling activation (level 4 → non-4 transitions).
    fan_at_level_4: bool = False


# ── Welford online statistics ─────────────────────────────────────────────────

class WelfordEMA:
    """Online mean and variance using Welford's one-pass algorithm.

    Stores (mean, M2, n).  variance = M2/n when n > 1.
    No circular buffer — O(1) space and O(1) update per sample.
    """

    __slots__ = ("mean", "m2", "n")

    def __init__(self) -> None:
        self.mean: float = 0.0
        self.m2: float = 0.0
        self.n: int = 0

    def update(self, value: float) -> None:
        self.n += 1
        delta = value - self.mean
        self.mean += delta / self.n
        self.m2 += delta * (value - self.mean)

    @property
    def variance(self) -> float | None:
        return (self.m2 / self.n) if self.n > 1 else None

    @property
    def std(self) -> float | None:
        v = self.variance
        return math.sqrt(v) if v is not None and v > 0.0 else None

    def z_score(self, value: float) -> float | None:
        s = self.std
        if s is None or s < 1e-9:
            return None
        return (value - self.mean) / s

    def is_established(self, min_n: int) -> bool:
        return self.n >= min_n

    def to_dict(self) -> dict[str, Any]:
        return {"mean": self.mean, "m2": self.m2, "n": self.n}

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "WelfordEMA":
        obj = cls()
        if d:
            obj.mean = float(d.get("mean", 0.0))
            obj.m2 = float(d.get("m2", 0.0))
            obj.n = int(d.get("n", 0))
        return obj


# ── Bypass tracker ────────────────────────────────────────────────────────────

def _is_bypass_open(status: str | None) -> bool | None:
    """Normalise bypass status string to open/closed/unknown."""
    if not status:
        return None
    s = status.lower()
    if "offen" in s or "open" in s:
        return True
    if "zu" in s or "closed" in s:
        return False
    return None


class BypassTracker:
    """Tracks bypass state transitions and episode statistics."""

    def __init__(self) -> None:
        self._last_is_open: bool | None = None
        self._state_since: float = 0.0
        self._open_episodes: deque[float] = deque(maxlen=MAX_BYPASS_EPISODES)
        self._closed_episodes: deque[float] = deque(maxlen=MAX_BYPASS_EPISODES)
        self._transitions: deque[float] = deque(maxlen=MAX_TRANSITIONS)
        # Cumulative for open fraction
        self._total_seconds: float = 0.0
        self._open_seconds: float = 0.0

    def update(
        self,
        status: str | None,
        timestamp: float,
        poll_interval_s: float = 30.0,
    ) -> None:
        is_open = _is_bypass_open(status)
        if is_open is None:
            return

        self._total_seconds += poll_interval_s
        if is_open:
            self._open_seconds += poll_interval_s

        if self._last_is_open is None:
            self._last_is_open = is_open
            self._state_since = timestamp
            return

        if is_open != self._last_is_open:
            duration_min = (timestamp - self._state_since) / 60.0
            if duration_min > 0.5:  # ignore sub-30s transients
                if self._last_is_open:
                    self._open_episodes.append(duration_min)
                else:
                    self._closed_episodes.append(duration_min)
            self._transitions.append(timestamp)
            self._last_is_open = is_open
            self._state_since = timestamp

    def transitions_in_window(
        self, now: float, window_s: float = BYPASS_HUNT_WINDOW_S
    ) -> int:
        cutoff = now - window_s
        return sum(1 for t in self._transitions if t >= cutoff)

    def is_hunting(self, now: float) -> bool:
        if self.transitions_in_window(now) >= BYPASS_HUNT_COUNT:
            return True
        avg = self.avg_open_episode_min
        if (
            avg is not None
            and len(self._open_episodes) >= 3
            and avg < BYPASS_HUNT_EPISODE_MIN
        ):
            return True
        return False

    @property
    def avg_open_episode_min(self) -> float | None:
        if not self._open_episodes:
            return None
        return round(sum(self._open_episodes) / len(self._open_episodes), 1)

    @property
    def avg_closed_episode_min(self) -> float | None:
        if not self._closed_episodes:
            return None
        return round(sum(self._closed_episodes) / len(self._closed_episodes), 1)

    @property
    def open_fraction_pct(self) -> float | None:
        if self._total_seconds < 3600.0:
            return None
        return round(self._open_seconds / self._total_seconds * 100.0, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "open_episodes": list(self._open_episodes),
            "closed_episodes": list(self._closed_episodes),
            "transitions": list(self._transitions),
            "total_seconds": self._total_seconds,
            "open_seconds": self._open_seconds,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "BypassTracker":
        obj = cls()
        if d:
            obj._open_episodes = deque(
                d.get("open_episodes", []), maxlen=MAX_BYPASS_EPISODES
            )
            obj._closed_episodes = deque(
                d.get("closed_episodes", []), maxlen=MAX_BYPASS_EPISODES
            )
            obj._transitions = deque(
                d.get("transitions", []), maxlen=MAX_TRANSITIONS
            )
            obj._total_seconds = float(d.get("total_seconds", 0.0))
            obj._open_seconds = float(d.get("open_seconds", 0.0))
        return obj


# ── Night cooling tracker ─────────────────────────────────────────────────────

def _in_night_window(local_hour: int) -> bool:
    """True wenn die Stunde innerhalb des 22:00-07:00 Fensters liegt."""
    return local_hour >= NIGHT_WINDOW_START_HOUR or local_hour < NIGHT_WINDOW_END_HOUR


def _window_id_for(timestamp: float) -> str:
    """Eindeutige ID fuer das Nachtfenster zu dem dieser Zeitpunkt gehoert.

    Das Fenster 22:00-07:00 ueberspannt Mitternacht -- Stunden 0-6 gehoeren
    zum Fenster das am VORTAG um 22:00 begonnen hat. Die ID ist das Datum
    des Fenster-Starts (22:00-Termin), unabhaengig davon ob der aktuelle
    Zeitpunkt vor oder nach Mitternacht liegt.
    """
    lt = time.localtime(timestamp)
    if lt.tm_hour < NIGHT_WINDOW_END_HOUR:
        # Gehoert zum Fenster das gestern Abend begann
        anchor = timestamp - 86400.0
        lt = time.localtime(anchor)
    return time.strftime("%Y-%m-%d", lt)


class NightCoolingTracker:
    """Misst den Nachtkuehlungserfolg im festen Zeitfenster 22:00-07:00 Uhr.

    Im Gegensatz zu einer reinen Session-Erkennung (Stufe4-Start bis Stufe4-Ende)
    ist diese Methode robust gegen kurze Unterbrechungen -- z.B. wenn das Geraet
    nach ca. 2h intern auf eine niedrigere Stufe zurueckfaellt und die HA-Automation
    Sekunden spaeter wieder korrigiert. Solche Korrekturzyklen wuerden eine
    session-basierte Erkennung in viele kleine Fragmente zerreissen, von denen
    keines die Mindestschwelle erreicht.

    Erfasst pro Nacht zusaetzlich zum reinen Delta:
    - aktive Minuten mit Stufe 4 (Aktivitaets-Normalisierung)
    - Effizienz in K pro aktiver Stunde (trennt Kuehlerfolg von reiner
      natuerlicher Nachtabkuehlung)
    - Bypass-Offen-Anteil waehrend der aktiven Kuehlzeit (deckt auf wenn die
      Bypass-Strategie nicht mitspielt, selbst wenn Stufe 4 nominell lief)
    - durchschnittliches thermisches Potenzial (T_abluft - T_aussenluft)
      waehrend der aktiven Kuehlzeit (war die Nacht ueberhaupt geeignet?)
    """

    def __init__(self) -> None:
        self._events: deque[dict[str, Any]] = deque(maxlen=MAX_NIGHT_EVENTS)
        # Jedes abgeschlossene Fenster, AUCH ohne Stufe-4-Aktivitaet -- separat
        # von _events, da hier die Inaktivitaets-/Aktivitaets-Trends herkommen,
        # unabhaengig davon ob ein Kuehlerfolg erzielt wurde.
        self._summaries: deque[dict[str, Any]] = deque(maxlen=MAX_NIGHT_SUMMARIES)

        # Zustand des aktuell offenen Fensters (None wenn kein Fenster aktiv)
        self._window_active: bool = False
        self._window_id: str | None = None
        self._start_temp: float | None = None
        self._start_ts: float | None = None

        # Akkumulatoren fuer das aktuell offene Fenster
        self._active_level4_seconds: float = 0.0
        self._bypass_open_seconds: float = 0.0
        self._potential_sum: float = 0.0
        self._potential_n: int = 0

    def update(
        self,
        fan_at_4: bool,
        temp_abluft: float | None,
        temp_aussenluft: float | None,
        bypass_open: bool | None,
        timestamp: float,
        poll_interval_s: float = 30.0,
    ) -> None:
        in_window = _in_night_window(time.localtime(timestamp).tm_hour)

        if in_window and not self._window_active:
            # Neues Fenster beginnt
            self._window_active = True
            self._window_id = _window_id_for(timestamp)
            self._start_temp = temp_abluft
            self._start_ts = timestamp
            self._active_level4_seconds = 0.0
            self._bypass_open_seconds = 0.0
            self._potential_sum = 0.0
            self._potential_n = 0

        elif not in_window and self._window_active:
            # Fenster endet jetzt -- abschliessen und Ereignis aufzeichnen
            self._finalize_window(temp_abluft, timestamp)
            self._window_active = False
            self._window_id = None
            self._start_temp = None
            self._start_ts = None

        if in_window and self._window_active:
            if fan_at_4:
                self._active_level4_seconds += poll_interval_s
                if bypass_open:
                    self._bypass_open_seconds += poll_interval_s
                if temp_abluft is not None and temp_aussenluft is not None:
                    self._potential_sum += (temp_abluft - temp_aussenluft)
                    self._potential_n += 1

    def _finalize_window(self, end_temp: float | None, end_ts: float) -> None:
        if self._start_temp is None or end_temp is None:
            return

        active_minutes = round(self._active_level4_seconds / 60.0, 1)

        # Jedes abgeschlossene Fenster wird als Summary erfasst -- unabhaengig
        # vom Kuehlerfolg. Das ist die Grundlage fuer Inaktivitaets-Erkennung:
        # eine Nacht ohne jede Stufe-4-Aktivitaet ist ein Automations-Problem,
        # kein Kuehlerfolg, egal wie stark die natuerliche Abkuehlung war.
        self._summaries.append({"ts": end_ts, "active_minutes": active_minutes})

        if self._active_level4_seconds <= 0:
            # Stufe 4 wurde in diesem Fenster nie gesetzt -- kein Kuehlereignis,
            # selbst wenn die Temperatur alleine durch natuerliche naechtliche
            # Abkuehlung gefallen ist. Sonst wuerde eine inaktive Automation
            # faelschlich als "Erfolg" durchgehen.
            return

        delta = self._start_temp - end_temp
        if delta < NIGHT_COOLING_MIN_DELTA_K:
            return  # Kein nennenswerter Kuehlerfolg -- kein Eintrag

        active_hours = self._active_level4_seconds / 3600.0
        efficiency = round(delta / active_hours, 2) if active_hours > 0.05 else None
        bypass_pct = (
            round(self._bypass_open_seconds / self._active_level4_seconds * 100.0, 1)
            if self._active_level4_seconds > 0
            else None
        )
        avg_potential = (
            round(self._potential_sum / self._potential_n, 2)
            if self._potential_n > 0
            else None
        )

        self._events.append({
            "ts": end_ts,
            "delta_k": round(delta, 2),
            "active_minutes": round(self._active_level4_seconds / 60.0, 1),
            "efficiency_k_per_h": efficiency,
            "bypass_open_pct": bypass_pct,
            "avg_potential_k": avg_potential,
        })

    @property
    def last_event(self) -> dict[str, Any] | None:
        return self._events[-1] if self._events else None

    @property
    def last_event_k(self) -> float | None:
        ev = self.last_event
        return ev["delta_k"] if ev else None

    @property
    def last_active_minutes(self) -> float | None:
        ev = self.last_event
        return ev["active_minutes"] if ev else None

    @property
    def last_efficiency_k_per_h(self) -> float | None:
        ev = self.last_event
        return ev["efficiency_k_per_h"] if ev else None

    @property
    def last_bypass_open_pct(self) -> float | None:
        ev = self.last_event
        return ev["bypass_open_pct"] if ev else None

    @property
    def last_avg_potential_k(self) -> float | None:
        ev = self.last_event
        return ev["avg_potential_k"] if ev else None

    def avg_k(self, window_days: float = 7.0) -> float | None:
        cutoff = time.time() - window_days * 86400.0
        recent = [e["delta_k"] for e in self._events if e["ts"] >= cutoff]
        return round(sum(recent) / len(recent), 2) if recent else None

    def avg_efficiency_k_per_h(self, window_days: float = 7.0) -> float | None:
        cutoff = time.time() - window_days * 86400.0
        recent = [
            e["efficiency_k_per_h"] for e in self._events
            if e["ts"] >= cutoff and e["efficiency_k_per_h"] is not None
        ]
        return round(sum(recent) / len(recent), 2) if recent else None

    def inactive_nights(self, window_days: float = 7.0) -> int:
        """Anzahl Naechte ohne jede Stufe-4-Aktivitaet im Zeitfenster.

        Hohe Werte deuten auf ein Automations- oder Konfigurationsproblem hin --
        unabhaengig von der tatsaechlichen Kuehlwirkung.
        """
        cutoff = time.time() - window_days * 86400.0
        return sum(
            1 for s in self._summaries
            if s["ts"] >= cutoff and s["active_minutes"] <= 0
        )

    def avg_active_minutes(self, window_days: float = 7.0) -> float | None:
        """Durchschnittliche Stufe-4-Laufzeit ueber ALLE Naechte im Fenster,

        auch jene ohne Kuehlerfolg. Ein ploetzlicher Rueckgang ist ein
        Fruehindikator fuer ein Automatisierungsproblem, bevor es sich im
        K-Wert zeigt.
        """
        cutoff = time.time() - window_days * 86400.0
        recent = [s["active_minutes"] for s in self._summaries if s["ts"] >= cutoff]
        return round(sum(recent) / len(recent), 1) if recent else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "events": list(self._events),
            "summaries": list(self._summaries),
            "window_active": self._window_active,
            "window_id": self._window_id,
            "start_temp": self._start_temp,
            "start_ts": self._start_ts,
            "active_level4_seconds": self._active_level4_seconds,
            "bypass_open_seconds": self._bypass_open_seconds,
            "potential_sum": self._potential_sum,
            "potential_n": self._potential_n,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "NightCoolingTracker":
        obj = cls()
        if not d:
            return obj

        raw_events = d.get("events", [])
        parsed: list[dict[str, Any]] = []
        for e in raw_events:
            if isinstance(e, dict):
                parsed.append(e)
            elif isinstance(e, (list, tuple)) and len(e) == 2:
                # Altformat (v1.4.0): [timestamp, delta_k] -- als Minimal-Eintrag uebernehmen
                parsed.append({
                    "ts": float(e[0]),
                    "delta_k": float(e[1]),
                    "active_minutes": None,
                    "efficiency_k_per_h": None,
                    "bypass_open_pct": None,
                    "avg_potential_k": None,
                })
        obj._events = deque(parsed, maxlen=MAX_NIGHT_EVENTS)
        obj._summaries = deque(d.get("summaries", []), maxlen=MAX_NIGHT_SUMMARIES)

        obj._window_active = bool(d.get("window_active", False))
        obj._window_id = d.get("window_id")
        obj._start_temp = d.get("start_temp")
        obj._start_ts = d.get("start_ts")
        obj._active_level4_seconds = float(d.get("active_level4_seconds", 0.0))
        obj._bypass_open_seconds = float(d.get("bypass_open_seconds", 0.0))
        obj._potential_sum = float(d.get("potential_sum", 0.0))
        obj._potential_n = int(d.get("potential_n", 0))
        return obj


# ── Main analytics class ──────────────────────────────────────────────────────

class KWLAnalytics:
    """Self-calibrating analytics engine for KWL diagnostics.

    Lifecycle
    ---------
    1. coordinator.async_setup() calls KWLAnalytics.from_dict(await store.async_load())
    2. coordinator._async_update_data() calls analytics.update(snapshot)
    3. Coordinator schedules store.async_delay_save(analytics.to_dict, 1800)
    4. HA flush writes to .storage/ on shutdown or after 30 min idle

    Alert suppression
    -----------------
    Alerts are suppressed via is_established() until MIN_N_* samples have been
    seen for the relevant baseline. The analytics_maturity_pct sensor exposes
    overall readiness so users understand why alerts may be inactive initially.

    Seasonal separation
    -------------------
    RPM and η baselines are maintained in two buckets: "summer" (T_aussenluft
    48h-EMA > 10°C) and "winter" (≤ 10°C). This prevents ~5% air-density
    variation from generating false RPM anomaly alerts across seasons.

    ε_exhaust and energy balance are winter-only — the gate conditions (bypass
    closed, delta > 5–8 K) are essentially never met in summer.
    """

    def __init__(self) -> None:
        # Season EMA
        self._au_ema: float | None = None

        # RPM baselines: season × level
        self._rpm: dict[str, dict[int, WelfordEMA]] = {
            "summer": {i: WelfordEMA() for i in range(1, 5)},
            "winter": {i: WelfordEMA() for i in range(1, 5)},
        }
        # Zu/Ab RPM ratio — single cross-season baseline
        self._ratio: WelfordEMA = WelfordEMA()

        # HRE baselines
        self._eta_summer: WelfordEMA = WelfordEMA()
        self._eta_winter: WelfordEMA = WelfordEMA()
        self._eps_exhaust: WelfordEMA = WelfordEMA()
        self._balance_ratio: WelfordEMA = WelfordEMA()

        # Trackers
        self._bypass = BypassTracker()
        self._night_cooling = NightCoolingTracker()

        # Last-computed values (updated on every poll, reset to None when ungated)
        self._season: str = "summer"
        self._last_ts: float = 0.0
        self._last_rpm_ab: float | None = None
        self._last_ratio: float | None = None
        self._last_eta: float | None = None       # fraction, not %
        self._last_eps: float | None = None       # fraction, not %
        self._last_balance: float | None = None
        self._last_rpm_z: float | None = None
        self._last_rpm_established: bool = False
        self._last_ratio_z: float | None = None

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, snap: KWLPollSnapshot, poll_interval_s: float = 30.0) -> None:
        """Process one poll. Called from coordinator._async_update_data()."""
        self._last_ts = snap.timestamp

        # ── Season ───────────────────────────────────────────────────────
        if snap.temp_aussenluft is not None:
            if self._au_ema is None:
                self._au_ema = snap.temp_aussenluft
            else:
                self._au_ema = (
                    SEASON_EMA_ALPHA * snap.temp_aussenluft
                    + (1.0 - SEASON_EMA_ALPHA) * self._au_ema
                )
            self._season = (
                "summer" if self._au_ema > SEASON_TEMP_THRESHOLD_C else "winter"
            )

        # ── Bypass ───────────────────────────────────────────────────────
        self._bypass.update(snap.bypass_status, snap.timestamp, poll_interval_s)

        # ── Night cooling ─────────────────────────────────────────────────
        self._night_cooling.update(
            fan_at_4=snap.fan_at_level_4,
            temp_abluft=snap.temp_abluft,
            temp_aussenluft=snap.temp_aussenluft,
            bypass_open=_is_bypass_open(snap.bypass_status),
            timestamp=snap.timestamp,
            poll_interval_s=poll_interval_s,
        )

        # ── RPM ───────────────────────────────────────────────────────────
        self._last_rpm_ab = None
        self._last_rpm_z = None
        self._last_rpm_established = False
        if (
            snap.rpm_abluft is not None
            and snap.current_level in (1, 2, 3, 4)
            and snap.rpm_abluft > 100.0
        ):
            self._last_rpm_ab = snap.rpm_abluft
            ema = self._rpm[self._season][snap.current_level]
            ema.update(snap.rpm_abluft)
            self._last_rpm_z = ema.z_score(snap.rpm_abluft)
            self._last_rpm_established = ema.is_established(MIN_N_RPM)

        # ── RPM ratio ────────────────────────────────────────────────────
        self._last_ratio = None
        self._last_ratio_z = None
        if (
            snap.rpm_abluft is not None
            and snap.rpm_zuluft is not None
            and snap.rpm_abluft > 100.0
        ):
            ratio = snap.rpm_zuluft / snap.rpm_abluft
            self._last_ratio = ratio
            self._ratio.update(ratio)
            self._last_ratio_z = self._ratio.z_score(ratio)

        # ── HRE metrics ───────────────────────────────────────────────────
        self._last_eta = None
        self._last_eps = None
        self._last_balance = None

        t_ab = snap.temp_abluft
        t_zu = snap.temp_zuluft
        t_au = snap.temp_aussenluft
        t_fo = snap.temp_fortluft

        if t_ab is not None and t_au is not None:
            delta = t_ab - t_au

            # Supply-side η (gate: delta ≥ 3 K — see HRE_MIN_DELTA_K)
            if delta >= HRE_MIN_DELTA_K and t_zu is not None:
                eta = (t_zu - t_au) / delta
                if 0.0 < eta < 1.2:
                    self._last_eta = eta
                    if self._season == "summer":
                        self._eta_summer.update(eta)
                    else:
                        self._eta_winter.update(eta)

            # Winter-only — ε_exhaust and energy balance
            if self._season == "winter" and delta >= HRE_WINTER_GATE_DELTA_K:
                if t_fo is not None:
                    eps = (t_ab - t_fo) / delta
                    if 0.0 < eps < 1.2:
                        self._last_eps = eps
                        self._eps_exhaust.update(eps)

                # Energy balance: strict gate — delta ≥ 8 K
                if (
                    delta >= ENERGY_BALANCE_GATE_K
                    and t_zu is not None
                    and t_fo is not None
                    and snap.rpm_abluft is not None
                    and snap.rpm_zuluft is not None
                    and snap.rpm_abluft > 100.0
                ):
                    zu_au_delta = t_zu - t_au
                    if zu_au_delta > 0.5:
                        balance = (t_ab - t_fo) / zu_au_delta
                        self._last_balance = balance
                        self._balance_ratio.update(balance)

    # ── Alert properties ──────────────────────────────────────────────────────

    @property
    def bypass_hunting(self) -> bool:
        return self._bypass.is_hunting(self._last_ts)

    @property
    def rpm_anomaly(self) -> bool:
        """True when abluft RPM is significantly below the level+season baseline.

        Only alerts on low RPM (motor bearing wear / degradation).
        High RPM at the same voltage would indicate reduced load, not a fault.
        Suppressed until MIN_N_RPM samples exist for current level+season.
        """
        if self._last_rpm_z is None or not self._last_rpm_established:
            return False
        return self._last_rpm_z < -RPM_ALERT_SIGMA

    @property
    def filter_clogging_suspected(self) -> bool:
        """True when abluft RPM is significantly ABOVE the level+season baseline.

        Community-Beitrag Torsten600 (Juni 2026): zunehmender Filterwiderstand
        zwingt den EC-Motor bei gleicher Stufe zu höherer Drehzahl, um den
        Volumenstrom zu halten -- ein früherer Indikator für Filterverstopfung
        als das feste zeitbasierte Filterintervall, besonders relevant in
        Umgebungen mit hoher Staub-/Pollenlast.

        Bewusst getrennt von rpm_anomaly: gleiche Baseline, aber entgegen-
        gesetzte Richtung und andere Ursache/Handlung (Filter wechseln statt
        Motor/Lager prüfen). Self-calibrating: nutzt die ohnehin vorhandene
        Stufe+Saison-Baseline -- kein zusätzlicher Hardware-Referenzwert nötig,
        funktioniert daher identisch für Touch- und Flex-Geräte.
        Suppressed until MIN_N_RPM samples exist for current level+season.
        """
        if self._last_rpm_z is None or not self._last_rpm_established:
            return False
        return self._last_rpm_z > RPM_HIGH_ALERT_SIGMA

    @property
    def ratio_anomaly(self) -> bool:
        """True when Zu/Ab RPM ratio deviates significantly from baseline.

        Detects asymmetric motor or filter degradation (one side changing
        relative to the other). Fires on deviation in either direction.
        """
        if not self._ratio.is_established(MIN_N_RATIO):
            return False
        if self._last_ratio_z is None:
            return False
        return abs(self._last_ratio_z) > RATIO_ALERT_SIGMA

    @property
    def eta_below_baseline(self) -> bool:
        """True when η has dropped ≥ 8 pp below the seasonal baseline mean.

        Uses the correct seasonal baseline (summer or winter).
        Suppressed until MIN_N_HRE gated readings exist.
        """
        if self._last_eta is None:
            return False
        ema = self._eta_summer if self._season == "summer" else self._eta_winter
        if not ema.is_established(MIN_N_HRE):
            return False
        return self._last_eta < ema.mean - ETA_ALERT_DELTA

    # ── Sensor value properties ───────────────────────────────────────────────

    @property
    def rpm_deviation_pct(self) -> float | None:
        """% deviation of current abluft RPM from level+season baseline mean.

        Negative = below baseline (motor wear signal).
        None when baseline not yet established or level unknown.
        """
        if self._last_rpm_z is None or self._last_rpm_ab is None:
            return None
        # Derive current level's EMA for the current season
        # We don't store the level in update — the z-score was computed
        # from the current EMA mean+std. Reconstruct deviation from z-score:
        # deviation_pct = z * (std / mean) * 100
        # Use the std and mean from the last-updated EMA is not directly accessible.
        # Simpler: store last_rpm_z and last_rpm_ab, compute pct from z+std+mean.
        # The z-score already encodes the deviation in std units.
        # Return z-score as a signed percentage of std for now.
        # TODO v1.5: store (level, season) at update time and read from EMA.
        return round(self._last_rpm_z * 100.0 / 33.0, 1) if self._last_rpm_z is not None else None

    @property
    def current_rpm_ratio(self) -> float | None:
        return round(self._last_ratio, 4) if self._last_ratio is not None else None

    @property
    def ratio_baseline_mean(self) -> float | None:
        return round(self._ratio.mean, 4) if self._ratio.n > 0 else None

    @property
    def bypass_open_pct(self) -> float | None:
        return self._bypass.open_fraction_pct

    @property
    def avg_bypass_open_min(self) -> float | None:
        return self._bypass.avg_open_episode_min

    @property
    def avg_bypass_closed_min(self) -> float | None:
        return self._bypass.avg_closed_episode_min

    @property
    def bypass_transitions_1h(self) -> int:
        return self._bypass.transitions_in_window(self._last_ts)

    @property
    def night_cooling_last_k(self) -> float | None:
        return self._night_cooling.last_event_k

    @property
    def night_cooling_7d_avg_k(self) -> float | None:
        return self._night_cooling.avg_k(7.0)

    @property
    def night_cooling_last_active_minutes(self) -> float | None:
        """Aktive Stufe-4-Minuten im letzten 22:00-07:00-Fenster."""
        return self._night_cooling.last_active_minutes

    @property
    def night_cooling_last_efficiency_k_per_h(self) -> float | None:
        """K Abkuehlung pro aktiver Stufe-4-Stunde -- trennt Kuehlerfolg

        von reiner natuerlicher Nachtabkuehlung. Hoher Wert = effiziente Nacht,
        niedriger Wert trotz langer Laufzeit deutet auf schwaches thermisches
        Potenzial oder eine Bypass-Stoerung hin.
        """
        return self._night_cooling.last_efficiency_k_per_h

    @property
    def night_cooling_7d_avg_efficiency_k_per_h(self) -> float | None:
        return self._night_cooling.avg_efficiency_k_per_h(7.0)

    @property
    def night_cooling_inactive_nights_7d(self) -> int:
        """Anzahl Naechte der letzten 7 Tage ohne jede Stufe-4-Aktivitaet.

        Reine Automations-/Konfigurationsgesundheitsmetrik -- unabhaengig
        von Temperaturerfolg. Hoher Wert deutet darauf hin dass die
        Sommer-Kuehlungs-Automation nicht wie erwartet auslöst.
        """
        return self._night_cooling.inactive_nights(7.0)

    @property
    def night_cooling_7d_avg_active_minutes(self) -> float | None:
        """Durchschnittliche Stufe-4-Laufzeit ueber alle Naechte der letzten

        7 Tage (auch Naechte ohne Kuehlerfolg). Fruehindikator fuer
        Automatisierungsprobleme, bevor sie sich im K-Wert zeigen.
        """
        return self._night_cooling.avg_active_minutes(7.0)

    @property
    def night_cooling_last_bypass_open_pct(self) -> float | None:
        """% der aktiven Stufe-4-Zeit mit offenem Bypass im letzten Fenster.

        Niedriger Wert trotz aktiver Stufe 4 zeigt eine Bypass-Stoerung auf,
        die sonst unsichtbar bliebe -- der Fan lief, aber die Kuehlluft
        wurde nicht durchgelassen.
        """
        return self._night_cooling.last_bypass_open_pct

    @property
    def night_cooling_last_avg_potential_k(self) -> float | None:
        """Durchschnittliches thermisches Potenzial (T_ab - T_au) waehrend

        der aktiven Kuehlzeit im letzten Fenster. Zeigt ob die Nacht ueberhaupt
        fuer Kuehlung geeignet war, unabhaengig vom tatsaechlichen Ergebnis.
        """
        return self._night_cooling.last_avg_potential_k

    @property
    def heat_recovery_efficiency_pct(self) -> float | None:
        """Supply-side η in percent, gated to delta ≥ 3 K."""
        return round(self._last_eta * 100.0, 1) if self._last_eta is not None else None

    @property
    def eps_exhaust_pct(self) -> float | None:
        """Exhaust-side HRE efficiency in percent (winter only)."""
        return round(self._last_eps * 100.0, 1) if self._last_eps is not None else None

    @property
    def energy_balance_ratio(self) -> float | None:
        """(T_ab−T_fo)/(T_zu−T_au). Expected ≈ RPM_zu/RPM_ab ≈ 1.20 (winter only)."""
        return round(self._last_balance, 3) if self._last_balance is not None else None

    @property
    def season(self) -> str:
        return self._season

    @property
    def au_temp_ema(self) -> float | None:
        return round(self._au_ema, 2) if self._au_ema is not None else None

    @property
    def analytics_maturity_pct(self) -> float:
        """0–100 %: fraction of baselines that have reached their minimum sample count.

        Summer RPM baselines establish within ~4 hours.
        Winter RPM and HRE baselines require seasonal conditions.
        Alerts from unestablished baselines are always suppressed regardless of this value.
        """
        checks: list[bool] = []
        for level in range(1, 5):
            checks.append(self._rpm["summer"][level].is_established(MIN_N_RPM))
            checks.append(self._rpm["winter"][level].is_established(MIN_N_RPM))
        checks.append(self._ratio.is_established(MIN_N_RATIO))
        checks.append(self._eta_summer.is_established(MIN_N_HRE))
        checks.append(self._eta_winter.is_established(MIN_N_HRE))
        checks.append(self._eps_exhaust.is_established(MIN_N_HRE))
        checks.append(self._balance_ratio.is_established(MIN_N_HRE))
        return round(sum(checks) / len(checks) * 100.0, 1) if checks else 0.0

    # ── Baseline management ───────────────────────────────────────────────────

    def reset_baselines(self) -> None:
        """Clear all learned baselines. Call after filter replacement."""
        self.__init__()  # type: ignore[misc]

    def rpm_level_baseline(self, level: int) -> float | None:
        """Baseline-RPM (Abluft) fuer eine Stufe aus dem selbstkalibrierenden EMA.

        Gibt None zurueck solange MIN_N_RPM Samples noch nicht erreicht sind.
        Wird von coordinator.rpm_reference_stufe4 genutzt fuer die dynamische
        Leistungsberechnung in power_current.
        """
        ema = self._rpm[self._season].get(level)
        if ema is not None and ema.is_established(MIN_N_RPM):
            return ema.mean
        return None

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": ANALYTICS_STORAGE_VERSION,
            "au_ema": self._au_ema,
            "season": self._season,
            "rpm": {
                season: {
                    str(level): ema.to_dict()
                    for level, ema in levels.items()
                }
                for season, levels in self._rpm.items()
            },
            "ratio": self._ratio.to_dict(),
            "eta_summer": self._eta_summer.to_dict(),
            "eta_winter": self._eta_winter.to_dict(),
            "eps_exhaust": self._eps_exhaust.to_dict(),
            "balance_ratio": self._balance_ratio.to_dict(),
            "bypass": self._bypass.to_dict(),
            "night_cooling": self._night_cooling.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "KWLAnalytics":
        """Deserialise from storage dict. Returns fresh instance on None."""
        obj = cls()
        if not d:
            return obj
        obj._au_ema = d.get("au_ema")
        obj._season = d.get("season", "summer")
        rpm_data = d.get("rpm", {})
        for season in ("summer", "winter"):
            for level in range(1, 5):
                obj._rpm[season][level] = WelfordEMA.from_dict(
                    rpm_data.get(season, {}).get(str(level))
                )
        obj._ratio = WelfordEMA.from_dict(d.get("ratio"))
        obj._eta_summer = WelfordEMA.from_dict(d.get("eta_summer"))
        obj._eta_winter = WelfordEMA.from_dict(d.get("eta_winter"))
        obj._eps_exhaust = WelfordEMA.from_dict(d.get("eps_exhaust"))
        obj._balance_ratio = WelfordEMA.from_dict(d.get("balance_ratio"))
        obj._bypass = BypassTracker.from_dict(d.get("bypass"))
        obj._night_cooling = NightCoolingTracker.from_dict(d.get("night_cooling"))
        return obj
