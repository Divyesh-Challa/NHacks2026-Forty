"""Threshold gesture detectors with refractory periods, plus the Pipeline that runs them.

Each detector consumes filtered samples (see filters.py) and returns Detection / NearMiss events.

- Detection: a gesture. confidence = 0.5 at the threshold, rising to 1.0 at twice the threshold.
- NearMiss: something clearly above the noise (past `floor`) that never reached `threshold`.
  Live, there's no ground truth for "the user tried and we missed it" — a near-miss is the best
  proxy, so it counts as a failed attempt in reliability. When eye control weakens, saccades
  shrink below threshold but stay above the floor, and reliability falls for a real reason.

Detectors:
- EogDetector (A0): look_left / look_right. level = (x − baseline). The baseline follows slow
  drift but freezes while |level| > floor, so returning the eyes to centre brings level back to ~0
  instead of firing the opposite direction. Must stay past threshold `eog_confirm_ms` (no spikes).
- BlinkDetector (A1): a blink is a short (< blink_max_ms) positive excursion past threshold; two
  within double_blink_ms = blink_double. Single blinks are ignored — people blink all the time.
- JawDetector (A2 envelope): a burst past threshold for ≥ jaw_min_ms, reported on release as
  jaw_clench. A burst still going after help_hold_ms is reported once, immediately, as jaw_hold —
  and never also as jaw_clench (HELP contract, TASKS.md).

`gain` on each detector is the demo degrade knob for real hardware: it scales the signal so
gestures land below threshold, exactly as a weakening muscle would.
"""

from dataclasses import dataclass

import numpy as np

from config import DETECTORS, HELP_HOLD_MS, SIGNAL
from filters import FS, EmgEnvelope, EogFilter


@dataclass
class Detection:
    source: str
    gesture: str
    confidence: float
    ts: int  # device time, ms


@dataclass
class NearMiss:
    source: str
    peak: float
    ts: int


Event = Detection | NearMiss


def confidence(peak: float, threshold: float) -> float:
    return float(np.clip(0.5 + 0.5 * (peak - threshold) / threshold, 0.0, 1.0))


class Baseline:
    """Slow EMA of the signal that only updates while the signal is at rest."""

    def __init__(self, fs: float, tau_s: float = SIGNAL["eog_baseline_s"]) -> None:
        self.alpha = 1.0 - np.exp(-1.0 / (fs * tau_s))
        self.value: float | None = None

    def update(self, x: float) -> None:
        self.value = x if self.value is None else self.value + self.alpha * (x - self.value)


class _Excursion:
    """Shared state for 'signal leaves baseline, peaks, comes back'."""

    def __init__(self, fs: float, threshold: float, floor: float) -> None:
        self.fs = fs
        self.threshold, self.floor = threshold, floor
        self.gain = 1.0
        self.base = Baseline(fs)
        self.refractory_us = SIGNAL["refractory_ms"] * 1000
        self.max_us = DETECTORS["max_excursion_s"] * 1e6
        self.active = False
        self.ready_at = 0
        self.sign = 0
        self.peak = 0.0
        self.start = 0

    def level(self, x: float) -> float:
        if self.base.value is None:
            self.base.update(x)
        return (x - self.base.value) * self.gain


class EogDetector(_Excursion):
    source = "eog_h"

    def __init__(self, fs: float = FS, settings: dict = DETECTORS) -> None:
        super().__init__(fs, settings["eog_threshold"], settings["eog_floor"])
        self.polarity = -1.0 if settings["eog_invert"] else 1.0
        self.confirm_us = settings["eog_confirm_ms"] * 1000
        self.emitted = False
        self.above_since: int | None = None

    def process(self, x: np.ndarray, t_us: np.ndarray) -> list[Event]:
        out: list[Event] = []
        for xi, ti in zip(x, t_us):
            lv = self.level(xi) * self.polarity
            if not self.active:
                self.base.update(xi)
                if abs(lv) > self.floor and ti >= self.ready_at:
                    self.active, self.sign, self.peak, self.start = True, int(np.sign(lv)), abs(lv), ti
                    self.emitted, self.above_since = False, None
                continue
            m = lv * self.sign
            self.peak = max(self.peak, m)
            if not self.emitted:
                if m > self.threshold:
                    self.above_since = ti if self.above_since is None else self.above_since
                    if ti - self.above_since >= self.confirm_us:
                        gesture = "look_left" if self.sign < 0 else "look_right"
                        out.append(Detection(self.source, gesture, confidence(self.peak, self.threshold), int(ti // 1000)))
                        self.emitted = True
                else:
                    self.above_since = None
            if m < self.floor / 2:  # eyes back at centre
                if not self.emitted:
                    out.append(NearMiss(self.source, self.peak, int(ti // 1000)))
                self.active = False
                self.ready_at = ti + (self.refractory_us if self.emitted else 0)
            elif ti - self.start > self.max_us:  # stuck off-baseline: electrode moved; start over here
                self.active = False
                self.base.value = xi
        return out


class BlinkDetector(_Excursion):
    source = "blink"

    def __init__(self, fs: float = FS, settings: dict = DETECTORS) -> None:
        super().__init__(fs, settings["blink_threshold"], settings["blink_floor"])
        self.blink_max_us = settings["blink_max_ms"] * 1000
        self.pair_us = settings["double_blink_ms"] * 1000
        self.last_blink: tuple[int, float] | None = None  # (start ts, peak)
        self.last_miss = -(10**12)

    def process(self, x: np.ndarray, t_us: np.ndarray) -> list[Event]:
        out: list[Event] = []
        for xi, ti in zip(x, t_us):
            lv = self.level(xi)
            if not self.active:
                self.base.update(xi)
                if lv > self.floor and ti >= self.ready_at:
                    self.active, self.peak, self.start = True, lv, ti
                continue
            self.peak = max(self.peak, lv)
            if lv < self.floor / 2:
                self.active = False
                out += self._ended(ti)
            elif ti - self.start > self.max_us:
                self.active = False
                self.base.value = xi
        return out

    def _ended(self, ti: int) -> list[Event]:
        if ti - self.start > self.blink_max_us:
            return []  # a vertical look, not a blink
        if self.peak < self.threshold:
            # Both halves of a weak double blink are one near-miss, not two.
            if self.start - self.last_miss > self.pair_us:
                self.last_miss = self.start
                return [NearMiss(self.source, self.peak, int(ti // 1000))]
            return []
        if self.last_blink and self.start - self.last_blink[0] <= self.pair_us:
            peak = min(self.peak, self.last_blink[1])
            self.last_blink = None
            self.ready_at = ti + self.refractory_us
            return [Detection(self.source, "blink_double", confidence(peak, self.threshold), int(ti // 1000))]
        self.last_blink = (self.start, self.peak)
        return []


class JawDetector:
    source = "jaw"

    def __init__(self, fs: float = FS, settings: dict = DETECTORS, hold_ms: float = HELP_HOLD_MS) -> None:
        self.threshold, self.floor = settings["jaw_threshold"], settings["jaw_floor"]
        self.min_us = settings["jaw_min_ms"] * 1000
        self.hold_us = hold_ms * 1000
        self.refractory_us = SIGNAL["refractory_ms"] * 1000
        self.gain = 1.0
        self.active = False
        self.start = 0
        self.crossed_at: int | None = None
        self.held = False
        self.peak = 0.0
        self.ready_at = 0

    def process(self, env: np.ndarray, t_us: np.ndarray) -> list[Event]:
        out: list[Event] = []
        for ei, ti in zip(env, t_us):
            e = ei * self.gain
            if not self.active:
                if e > self.floor and ti >= self.ready_at:
                    self.active, self.start, self.peak, self.crossed_at, self.held = True, ti, e, None, False
                continue
            self.peak = max(self.peak, e)
            if e > self.threshold and self.crossed_at is None:
                self.crossed_at = ti
            if self.crossed_at is not None and not self.held and ti - self.crossed_at >= self.hold_us:
                out.append(Detection(self.source, "jaw_hold", confidence(self.peak, self.threshold), int(ti // 1000)))
                self.held = True
            if e < 0.75 * self.floor:  # released (hysteresis: no chatter around the floor)
                self.active = False
                if self.held:
                    self.ready_at = ti + self.refractory_us
                elif self.crossed_at is not None and ti - self.crossed_at >= self.min_us:
                    out.append(Detection(self.source, "jaw_clench", confidence(self.peak, self.threshold), int(ti // 1000)))
                    self.ready_at = ti + self.refractory_us
                elif self.crossed_at is None and ti - self.start >= self.min_us:
                    out.append(NearMiss(self.source, self.peak, int(ti // 1000)))
        return out


class Pipeline:
    """Raw Arduino rows (t_us, a0, a1, a2) in, gesture events out. Streaming."""

    def __init__(self, fs: float = FS, settings: dict | None = None) -> None:
        s = {**DETECTORS, **(settings or {})}
        self.filters = (EogFilter(fs), EogFilter(fs), EmgEnvelope(fs))
        self.eog = EogDetector(fs, s)
        self.blink = BlinkDetector(fs, s)
        self.jaw = JawDetector(fs, s)
        self.detectors = {"eog_h": self.eog, "blink": self.blink, "jaw": self.jaw}
        self.last_features: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None

    def set_gain(self, signal: str, factor: float) -> None:
        for s in ["eog_h", "blink"] if signal == "eye" else [signal]:
            if s in self.detectors:
                self.detectors[s].gain = factor

    def features(self, rows: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Filtered traces (EOG-H, EOG-V, jaw envelope) — for plotting and calibration."""
        rows = np.asarray(rows).reshape(-1, 4)
        return tuple(f(rows[:, i + 1].astype(float)) for i, f in enumerate(self.filters))

    def process(self, rows: np.ndarray) -> list[Event]:
        rows = np.asarray(rows).reshape(-1, 4)
        if rows.size == 0:
            return []
        h, v, env = self.last_features = self.features(rows)
        t = rows[:, 0]
        events = self.eog.process(h, t) + self.blink.process(v, t) + self.jaw.process(env, t)
        return sorted(events, key=lambda e: e.ts)
