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
- VerticalEogDetector (A1): look_up / look_down from the shape of a short pulse pair.

`gain` on each detector is the demo degrade knob for real hardware: it scales the signal so
gestures land below threshold, exactly as a weakening muscle would.
"""

from dataclasses import dataclass

import numpy as np

from config import DETECTORS, SIGNAL
from filters import FS, EogFilter


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
    prefix = "eog"  # settings keys: {prefix}_threshold / _floor / _invert / _confirm_ms
    names = ("look_left", "look_right")  # (negative, positive) excursion

    def __init__(self, fs: float = FS, settings: dict = DETECTORS) -> None:
        p = self.prefix
        super().__init__(fs, settings[f"{p}_threshold"], settings[f"{p}_floor"])
        self.polarity = -1.0 if settings[f"{p}_invert"] else 1.0
        self.confirm_us = settings[f"{p}_confirm_ms"] * 1000
        self.min_miss_us = 0  # excursions shorter than this are not reported as near-misses
        # The pill is AC-coupled: a held look fades, so coming back to centre overshoots to the other
        # side by the faded amount and reads as a look the other way. Ignore that for rearm_ms.
        self.rearm_us = settings.get(f"{p}_rearm_ms", 0) * 1000
        self.rearm_until, self.rearm_sign = 0, 0
        self.emitted = False
        self.above_since: int | None = None

    def process(self, x: np.ndarray, t_us: np.ndarray) -> list[Event]:
        out: list[Event] = []
        for xi, ti in zip(x, t_us):
            lv = self.level(xi) * self.polarity
            if not self.active:
                self.base.update(xi)
                return_stroke = ti < self.rearm_until and int(np.sign(lv)) == -self.rearm_sign
                if abs(lv) > self.floor and ti >= self.ready_at and not return_stroke:
                    self.active, self.sign, self.peak, self.start = True, int(np.sign(lv)), abs(lv), ti
                    self.emitted, self.above_since = False, None
                continue
            m = lv * self.sign
            self.peak = max(self.peak, m)
            if not self.emitted:
                if m > self.threshold:
                    self.above_since = ti if self.above_since is None else self.above_since
                    if ti - self.above_since >= self.confirm_us:
                        gesture = self.names[0] if self.sign < 0 else self.names[1]
                        out.append(Detection(self.source, gesture, confidence(self.peak, self.threshold), int(ti // 1000)))
                        self.emitted = True
                else:
                    self.above_since = None
            if m < self.floor / 2:  # eyes back at centre
                if not self.emitted and ti - self.start >= self.min_miss_us:
                    out.append(NearMiss(self.source, self.peak, int(ti // 1000)))
                self.active = False
                self.ready_at = ti + (self.refractory_us if self.emitted else 0)
                if self.emitted:
                    self.rearm_until, self.rearm_sign = ti + self.rearm_us, self.sign
            elif ti - self.start > self.max_us:  # stuck off-baseline: electrode moved; start over here
                self.active = False
                self.base.value = xi
        return out


class VerticalEogDetector:
    """A1 look up / look down, told apart from blinks by pulse *shape*, not length.

    On the AC-coupled pill a look is a ~100-150 ms pulse, the same length as a blink (measured), so
    a long hold can't be required. What differs: a blink is a positive spike followed within
    vert_pair_ms by a deep negative trough (and usually a second spike); a look up is a positive
    pulse with no such trough; a look down is a negative pulse with no positive spike just before it.
    A look up is therefore reported vert_pair_ms after the pulse, once no trough or second spike came.
    No near-misses are emitted (ponytail: eog_v reliability never falls; add them if it must remap).
    """

    source = "eog_v"

    def __init__(self, fs: float = FS, settings: dict = DETECTORS) -> None:
        self.threshold, self.floor = settings["vert_threshold"], settings["vert_floor"]
        self.polarity = -1.0 if settings["vert_invert"] else 1.0
        self.pair_us = settings.get("vert_pair_ms", 350) * 1000
        self.rearm_us = settings.get("vert_rearm_ms", 0) * 1000  # return-to-centre overshoot, as in EogDetector
        self.refractory_us = SIGNAL["refractory_ms"] * 1000
        self.max_us = DETECTORS["max_excursion_s"] * 1e6
        self.gain = 1.0
        self.base = Baseline(fs)
        self.active = False
        self.sign, self.peak, self.start = 0, 0.0, 0
        self.last_pos_end = -(10**12)
        self.pending: tuple[int, float] | None = None  # (end, peak) of a positive pulse not yet proven a look
        self.ready_at = 0
        self.rearm_until, self.rearm_sign = 0, 0

    def process(self, x: np.ndarray, t_us: np.ndarray) -> list[Event]:
        out: list[Event] = []
        for xi, ti in zip(x, t_us):
            if self.base.value is None:
                self.base.update(xi)
            lv = (xi - self.base.value) * self.gain * self.polarity
            if self.pending and not self.active and ti - self.pending[0] >= self.pair_us:
                out += self._emit("look_up", self.pending[1], ti)
                self.pending = None
            if not self.active:
                self.base.update(xi)
                if abs(lv) > self.floor:
                    self.active, self.sign, self.peak, self.start = True, int(np.sign(lv)), abs(lv), ti
                continue
            self.peak = max(self.peak, lv * self.sign)
            if lv * self.sign < self.floor / 2:
                self.active = False
                out += self._pulse(self.sign, self.peak, self.start, ti)
            elif ti - self.start > self.max_us:  # stuck off-baseline: electrode moved; start over here
                self.active = False
                self.base.value = xi
        return out

    def _pulse(self, sign: int, peak: float, start: int, end: int) -> list[Event]:
        if sign > 0:
            second_spike = self.pending is not None and start - self.pending[0] <= self.pair_us
            self.last_pos_end = end
            self.pending = None if second_spike else ((end, peak) if peak >= self.threshold else None)
            return []
        if self.pending and start - self.pending[0] <= self.pair_us and peak >= 0.5 * self.pending[1]:
            self.pending = None  # the trough after a blink spike
            return []
        if peak >= self.threshold and start - self.last_pos_end > self.pair_us:
            return self._emit("look_down", peak, end)
        return []

    def _emit(self, gesture: str, peak: float, ts: int) -> list[Event]:
        sign = 1 if gesture == "look_up" else -1
        if ts < self.ready_at or (ts < self.rearm_until and sign == -self.rearm_sign):
            return []
        self.ready_at = ts + self.refractory_us
        self.rearm_until, self.rearm_sign = ts + self.rearm_us, sign
        return [Detection(self.source, gesture, confidence(peak, self.threshold), int(ts // 1000))]


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


class Pipeline:
    """Raw Arduino rows (t_us, a0, a1, a2) in, gesture events out. Streaming. A2 is ignored."""

    def __init__(self, fs: float = FS, settings: dict | None = None) -> None:
        s = {**DETECTORS, **(settings or {})}
        self.filters = (EogFilter(fs), EogFilter(fs))
        self.eog = EogDetector(fs, s)
        self.blink = BlinkDetector(fs, s)
        self.vert = VerticalEogDetector(fs, s)
        self.detectors = {"eog_h": self.eog, "blink": self.blink, "eog_v": self.vert}
        self.last_features: tuple[np.ndarray, np.ndarray] | None = None

    def set_gain(self, signal: str, factor: float) -> None:
        for s in ["eog_h", "eog_v"] if signal == "eye" else [signal]:
            if s in self.detectors:
                self.detectors[s].gain = factor

    def features(self, rows: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Filtered traces (EOG-H, EOG-V) — for plotting and calibration."""
        rows = np.asarray(rows).reshape(-1, 4)
        return tuple(f(rows[:, i + 1].astype(float)) for i, f in enumerate(self.filters))

    def process(self, rows: np.ndarray) -> list[Event]:
        rows = np.asarray(rows).reshape(-1, 4)
        if rows.size == 0:
            return []
        h, v = self.last_features = self.features(rows)
        t = rows[:, 0]
        events = self.eog.process(h, t) + self.blink.process(v, t) + self.vert.process(v, t)
        return sorted(events, key=lambda e: e.ts)
