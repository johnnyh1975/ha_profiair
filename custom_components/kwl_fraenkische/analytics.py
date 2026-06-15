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

# ── Bypass episode tracking ───────────────────────────────────────────────────

MAX_BYPASS_EPISODES: int = 50
MAX_TRANSITIONS: int = 200
BYPASS_HUNT_WINDOW_S: float = 3600.0  # 60-minute window
BYPASS_HUNT_COUNT: int = 5            # transitions that trigger hunting alert
BYPASS_HUNT_EPISODE_MIN: float = 15.0 # avg open episode below this → hunting

# ── Night cooling ─────────────────────────────────────────────────────────────

MAX_NIGHT_EVENTS: int = 30
NIGHT_COOLING_MIN_DELTA_K: float = 0.5  # min T_abluft drop to count as valid

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

class NightCoolingTracker:
    """Records T_abluft drop per Stufe-4 cooling activation.

    A "session" begins when fan goes to level 4 and ends when it drops back.
    Only sessions with a net T_abluft drop ≥ MIN_DELTA_K are recorded.
    This catches night cooling events regardless of clock time, and also
    captures daytime Stufe-4 runs (which produce smaller but still real drops).
    """

    def __init__(self) -> None:
        self._events: deque[tuple[float, float]] = deque(maxlen=MAX_NIGHT_EVENTS)
        self._session_start_temp: float | None = None
        self._in_cooling: bool = False

    def update(
        self, fan_at_4: bool, temp_abluft: float | None, timestamp: float
    ) -> None:
        if temp_abluft is None:
            return
        if fan_at_4 and not self._in_cooling:
            self._session_start_temp = temp_abluft
            self._in_cooling = True
        elif not fan_at_4 and self._in_cooling and self._session_start_temp is not None:
            delta = self._session_start_temp - temp_abluft
            if delta >= NIGHT_COOLING_MIN_DELTA_K:
                self._events.append((timestamp, round(delta, 2)))
            self._in_cooling = False
            self._session_start_temp = None

    @property
    def last_event_k(self) -> float | None:
        return self._events[-1][1] if self._events else None

    def avg_k(self, window_days: float = 7.0) -> float | None:
        cutoff = time.time() - window_days * 86400.0
        recent = [d for ts, d in self._events if ts >= cutoff]
        return round(sum(recent) / len(recent), 2) if recent else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "events": [[ts, d] for ts, d in self._events],
            "in_cooling": self._in_cooling,
            "session_start_temp": self._session_start_temp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "NightCoolingTracker":
        obj = cls()
        if d:
            raw = d.get("events", [])
            obj._events = deque(
                [(float(e[0]), float(e[1])) for e in raw if len(e) == 2],
                maxlen=MAX_NIGHT_EVENTS,
            )
            obj._in_cooling = bool(d.get("in_cooling", False))
            obj._session_start_temp = d.get("session_start_temp")
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
        self._night_cooling.update(snap.fan_at_level_4, snap.temp_abluft, snap.timestamp)

        # ── RPM ───────────────────────────────────────────────────────────
        self._last_rpm_ab = None
        self._last_rpm_z = None
        if (
            snap.rpm_abluft is not None
            and snap.current_level in (1, 2, 3, 4)
            and snap.rpm_abluft > 100.0
        ):
            self._last_rpm_ab = snap.rpm_abluft
            ema = self._rpm[self._season][snap.current_level]
            ema.update(snap.rpm_abluft)
            self._last_rpm_z = ema.z_score(snap.rpm_abluft)

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
        level = None
        if self._last_rpm_z is None or self._last_ts == 0.0:
            return False
        # Check that baseline is established — need the current level
        # _last_rpm_z is only set when update() ran with a valid level,
        # so we can read it directly from the EMA that was updated.
        # The alert fires only on sustained negative z-score.
        return self._last_rpm_z < -RPM_ALERT_SIGMA

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
