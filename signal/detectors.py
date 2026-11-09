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

import logging
from collections import deque

import numpy as np

from config import DETECTORS, SIGNAL
from filters import FS, EogFilter


log = logging.getLogger("relay.tracker")

LOOK_AXIS = {"look_left": ("h", -1), "look_right": ("h", 1), "look_up": ("v", 1), "look_down": ("v", -1)}


@dataclass
class Detection:
    source: str
    gesture: str
    confidence: float
    ts: int  # device time, ms
    peak: float = 0.0  # size of the pulse that produced it (looks only); the position tracker needs it
    confirmed: bool = True  # look up only: False = a lone positive pulse with no negative swing behind it
    swing: float = 0.0  # look up only: size of that negative swing


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
        self.confirmed = False
        self.above_since: int | None = None
        self.direction_settings = settings

    def _detection(self, ti: int) -> Detection:
        gesture = self.names[0] if self.sign < 0 else self.names[1]
        return Detection(self.source, gesture, confidence(self.peak, self.threshold), int(ti // 1000), float(self.peak))

    def process(self, x: np.ndarray, t_us: np.ndarray) -> list[Event]:
        out: list[Event] = []
        for xi, ti in zip(x, t_us):
            lv = self.level(xi) * self.polarity
            if not self.active:
                direction = self.names[0] if lv < 0 else self.names[1]
                self.threshold = self.direction_settings.get(f"{direction}_threshold", self.direction_settings[f"{self.prefix}_threshold"])
                self.floor = self.direction_settings.get(f"{direction}_floor", self.direction_settings[f"{self.prefix}_floor"])
                self.base.update(xi)
                return_stroke = ti < self.rearm_until and int(np.sign(lv)) == -self.rearm_sign
                # Opposite pulses must reach the zone tracker even during the refractory period:
                # otherwise a fast return is lost and the next genuine opposite look is swallowed.
                ready = ti >= self.ready_at or int(np.sign(lv)) != self.sign
                if abs(lv) > self.floor and ready and not return_stroke:
                    self.active, self.sign, self.peak, self.start = True, int(np.sign(lv)), abs(lv), ti
                    self.emitted, self.confirmed, self.above_since = False, False, None
                continue
            m = lv * self.sign
            self.peak = max(self.peak, m)
            if not self.confirmed:
                if m > self.threshold:
                    self.above_since = ti if self.above_since is None else self.above_since
                    if ti - self.above_since >= self.confirm_us:
                        self.confirmed = True
                else:
                    self.above_since = None
            # Report once the pulse has peaked (falls to 85% of its top), so the detection carries the
            # pulse's full size: a side-to-side sweep is twice a centre-to-side look (see _track_position).
            if self.confirmed and not self.emitted and m < 0.85 * self.peak:
                out.append(self._detection(ti))
                self.emitted = True
            if m < self.floor / 2:  # eyes back at centre
                if self.confirmed and not self.emitted:
                    out.append(self._detection(ti))
                    self.emitted = True
                elif not self.emitted and ti - self.start >= self.min_miss_us:
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
    Near-misses (a look-shaped pulse past the floor, short of threshold) are only reported while the
    signal is degraded (`misses`, set by Pipeline.set_gain / mark_degraded). At rest on the rig a small
    A1 pulse is as often a weak blink or noise as a weak look, and counting those would push eog_v,
    and with it the wheel, out while nothing is wrong. Under a degrade the person keeps trying looks
    that land short, and eog_v reliability has to fall with eog_h for one wheel -> scan switch.
    """

    source = "eog_v"

    def __init__(self, fs: float = FS, settings: dict = DETECTORS) -> None:
        self.threshold, self.floor = settings["vert_threshold"], settings["vert_floor"]
        self.thresholds = {1: settings.get("look_up_threshold", self.threshold), -1: settings.get("look_down_threshold", self.threshold)}
        self.floors = {1: settings.get("look_up_floor", self.floor), -1: settings.get("look_down_floor", self.floor)}
        self.polarity = -1.0 if settings["vert_invert"] else 1.0
        self.pair_us = settings.get("vert_pair_ms", 350) * 1000
        self.rearm_us = settings.get("vert_rearm_ms", 0) * 1000  # return-to-centre overshoot, as in EogDetector
        # A positive spike below this is a look, not a blink (blinks are ~180-320, up looks ~80-110).
        self.blink_min = 0.75 * (settings.get("blink_unit") or 2 * settings["blink_threshold"])
        # Rigs where a look up is biphasic (a positive pulse, then a negative swing of at least this
        # fraction): require it, so the lone positive pulse of coming back from a down isn't a look up.
        self.trough_ratio = settings.get("vert_up_trough_ratio", 0.0)
        self.pending_ok = False
        self.swing = 0.0
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
        self.misses = False
        self.last_end = -(10**12)  # end of the previous pulse of either sign

    def process(self, x: np.ndarray, t_us: np.ndarray) -> list[Event]:
        out: list[Event] = []
        for xi, ti in zip(x, t_us):
            if self.base.value is None:
                self.base.update(xi)
            lv = (xi - self.base.value) * self.gain * self.polarity
            if self.pending and not self.active and ti - self.pending[0] >= self.pair_us:
                # Always reported; `confirmed` says whether it had the negative swing behind it. The zone
                # tracker uses that: a lone positive pulse from centre is not a look, but from the down
                # zone it is the eyes coming back, and the tracker needs to see it to stay in step.
                out += self._emit("look_up", self.pending[1], ti, confirmed=self.pending_ok or self.trough_ratio <= 0, swing=self.swing)
                self.pending = None
            if not self.active:
                self.base.update(xi)
                sign = 1 if lv > 0 else -1
                if abs(lv) > self.floors[sign]:
                    self.active, self.sign, self.peak, self.start = True, int(np.sign(lv)), abs(lv), ti
                continue
            self.peak = max(self.peak, lv * self.sign)
            if lv * self.sign < self.floors[self.sign] / 2:
                self.active = False
                out += self._pulse(self.sign, self.peak, self.start, ti)
            elif ti - self.start > self.max_us:  # stuck off-baseline: electrode moved; start over here
                self.active = False
                self.base.value = xi
        return out

    def _pulse(self, sign: int, peak: float, start: int, end: int) -> list[Event]:
        # A pulse right after another is that one's trough, swing or second spike, never a look of its own.
        alone = start - self.last_end > self.pair_us
        self.last_end = end
        if sign > 0:
            second_spike = self.pending is not None and start - self.pending[0] <= self.pair_us
            if peak >= self.thresholds[1]:
                self.last_pos_end = end
            self.pending = None if second_spike else ((end, peak) if peak >= self.thresholds[1] else None)
            self.pending_ok = False
            self.swing = 0.0
            return self._miss(peak, end) if alone and peak < self.threshold else []
        if (
            self.pending
            and start - self.pending[0] <= self.pair_us
            and peak >= 0.35 * self.pending[1]
            and self.pending[1] >= self.blink_min * self.gain  # only a blink-sized spike has a blink's trough;
        ):  # a small look-up pulse is followed by an equally small negative swing (measured: ~60 / ~45)
            self.pending = None  # the trough after a blink spike
            return []
        if self.pending and start - self.pending[0] <= self.pair_us:
            need = self.trough_ratio * self.pending[1]
            if self.trough_ratio > 0:
                need = max(need, 0.6 * self.thresholds[1])
            if peak >= need:
                self.pending_ok = True  # the negative swing behind a look-up pulse
                self.swing = max(self.swing, peak)
        if peak >= self.thresholds[-1] and start - self.last_pos_end > self.pair_us:
            return self._emit("look_down", peak, end)
        return self._miss(peak, end) if alone and peak < self.threshold else []

    def _miss(self, peak: float, ts: int) -> list[Event]:
        if not self.misses or ts < self.ready_at or ts < self.rearm_until:
            return []
        return [NearMiss(self.source, peak, int(ts // 1000))]

    def _emit(self, gesture: str, peak: float, ts: int, confirmed: bool = True, swing: float = 0.0) -> list[Event]:
        sign = 1 if gesture == "look_up" else -1
        # The return-to-centre bounce after a vertical look has both signs (measured: a negative swing,
        # then a small positive one ~1.5 s later), so for vert_rearm_ms nothing else is reported.
        if ts < self.ready_at or ts < self.rearm_until:
            return []
        self.ready_at = ts + self.refractory_us
        self.rearm_until, self.rearm_sign = ts + self.rearm_us, sign
        return [Detection(self.source, gesture, confidence(peak, self.thresholds[sign]), int(ts // 1000), float(peak), confirmed, float(swing))]


class BlinkDetector(_Excursion):
    source = "blink"

    def __init__(self, fs: float = FS, settings: dict = DETECTORS) -> None:
        super().__init__(fs, settings["blink_threshold"], settings["blink_floor"])
        self.blink_max_us = settings["blink_max_ms"] * 1000
        self.pair_us = settings["double_blink_ms"] * 1000
        self.last_blink: tuple[int, float] | None = None  # (start ts, peak)
        self.last_miss = -(10**12)
        self.settle_us = 2_000_000  # after a blink, ignore the undershoot for the baseline for this long
        self.settle_until = 0
        self.armed = True
        self.last_valid_pulse: tuple[int, int] | None = None
        self.pulse_candidate: tuple[int, int, float] | None = None
        self.blink_min = .75 * (settings.get("blink_unit") or 2 * settings["blink_threshold"])
        self.shape_pair_us = settings.get("vert_pair_ms", 350) * 1000

    def process(self, x: np.ndarray, t_us: np.ndarray) -> list[Event]:
        out: list[Event] = []
        for xi, ti in zip(x, t_us):
            lv = self.level(xi)
            if self.pulse_candidate:
                start, end, peak = self.pulse_candidate
                if ti - end > self.shape_pair_us:
                    self.pulse_candidate = None
                elif lv <= -.35 * peak:
                    self.last_valid_pulse = (int(start // 1000), int(end // 1000))
                    self.pulse_candidate = None
            if not self.active:
                # A blink is followed by a deep undershoot (AC-coupled pill). Don't let the idle baseline
                # chase it down, or the resting level afterwards looks like a long positive excursion
                # above a frozen baseline and the second blink of a pair is swallowed.
                if ti >= self.settle_until or lv > -self.floor:
                    self.base.update(xi)
                if not self.armed and lv < self.floor / 2:
                    self.armed = True  # the tail of the last blink has fully come down
                if self.armed and lv > self.floor and ti >= self.ready_at:
                    self.active, self.peak, self.start = True, lv, ti
                continue
            self.peak = max(self.peak, lv)
            # A blink is over once it has fallen well away from its own peak. A fixed low line alone can
            # sit just under the resting level after the undershoot, so the pulse would never close.
            if lv < max(self.floor / 2, 0.35 * self.peak):
                self.active = False
                self.armed = lv < self.floor / 2  # still in the tail: wait for it to finish before reopening
                self.settle_until = ti + self.settle_us
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
        if self.peak >= self.blink_min:
            self.pulse_candidate = (int(self.start), int(ti), float(self.peak))
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
        self.h_guard_ms = s.get("vert_h_guard_ms", 700)  # drop up/down this close to a left/right event
        self.up_needs_swing = s.get("vert_up_trough_ratio", 0.0) > 0
        self.up_bounce_ms = s.get("vert_up_bounce_ms", 1200)
        self.up_swing_ratio = s.get("vert_up_swing_ratio", 0.3)
        self.last_up_ts = -10**12
        self.return_hold_ms = s.get("look_return_hold_ms", 8000)  # 0 turns the position tracking off
        # The vertical return arrives 1.8-2.8 s after a look, so past ~3.5 s the eyes are back at centre
        # and the next vertical pulse is a new look (a stale "up" zone swallowed real downs).
        self.axis_hold = {"h": self.return_hold_ms, "v": min(self.return_hold_ms, s.get("vert_return_hold_ms", 3500))}
        self.position: dict[str, tuple[int, int]] = {"h": (0, 0), "v": (0, 0)}  # axis -> (zone, ts of that look)
        # One unit = a centre-to-side look. A pulse at least sweep_ratio units big is a side-to-side sweep
        # (2 units). Vertical pulses are small and noisy, so its boundary is stricter.
        self.unit = {"h": s.get("eog_unit") or 2 * s["eog_threshold"], "v": s.get("vert_unit") or 2 * s["vert_threshold"]}
        self.sweep_ratio = {"h": s.get("eog_sweep_ratio", 1.5), "v": s.get("vert_sweep_ratio", 2.2)}
        # The same look again with no return between: vertical has a bounce (small pulses either side of
        # the return), horizontal returns are clean and detected, so its guard is off by default.
        self.repeat_guard_ms = {"h": s.get("eog_repeat_guard_ms", 0), "v": s.get("look_repeat_guard_ms", 3000)}
        self.direction_units = {g: s.get(f"{g}_unit", self.unit[axis]) for g, (axis, _) in LOOK_AXIS.items()}
        self.blink_guard_ms = s.get("vert_blink_guard_ms", 900)
        self.pending_vertical: deque[Detection] = deque()
        self.horizontal_times: deque[int] = deque()
        self.blink_intervals: deque[tuple[int, int]] = deque()

    def set_gain(self, signal: str, factor: float) -> None:
        for s in ["eog_h", "eog_v"] if signal == "eye" else [signal]:
            if s in self.detectors:
                self.detectors[s].gain = factor
        self.mark_degraded(signal, factor < 1)

    def mark_degraded(self, signal: str, on: bool) -> None:
        """Demo degrade on/off: eog_v reports near-misses only while degraded (see VerticalEogDetector).
        set_gain calls it; a synthetic source that shrinks the waveform itself calls it directly."""
        if signal in ("eye", "eog_v"):
            self.vert.misses = on

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
        out: list[Event] = []
        # Process in device-time order, regardless of serial read size. Hold vertical candidates long
        # enough to observe nearby horizontal looks / blinks on either side of their timestamp.
        for i, ti in enumerate(t):
            now = int(ti // 1000)
            horizontal = self.eog.process(h[i:i + 1], t[i:i + 1])
            self.horizontal_times.extend(e.ts for e in horizontal if isinstance(e, Detection))
            previous = self.blink.last_valid_pulse
            blinks = self.blink.process(v[i:i + 1], t[i:i + 1])
            if self.blink.last_valid_pulse != previous:
                self.blink_intervals.append(self.blink.last_valid_pulse)
            self.pending_vertical.extend(self.vert.process(v[i:i + 1], t[i:i + 1]))
            ready: list[Event] = horizontal + blinks
            delay = max(self.h_guard_ms, self.vert.pair_us / 1000)
            while self.pending_vertical and now - self.pending_vertical[0].ts >= delay:
                e = self.pending_vertical.popleft()
                cross = any(abs(e.ts - ts) <= self.h_guard_ms for ts in self.horizontal_times)
                blink = any(a - self.vert.pair_us / 1000 <= e.ts <= b + self.blink_guard_ms for a, b in self.blink_intervals)
                if not cross and not blink:
                    ready.append(e)
            # Retain enough history for delayed candidates; bounded even on long-running streams.
            cutoff = now - delay - max(self.h_guard_ms, self.blink_guard_ms) - 1000
            while self.horizontal_times and self.horizontal_times[0] < cutoff:
                self.horizontal_times.popleft()
            while self.blink_intervals and self.blink_intervals[0][1] < cutoff:
                self.blink_intervals.popleft()
            out.extend(self._track_position(sorted(ready, key=lambda e: e.ts)))
        return out

    def _track_position(self, events: list[Event]) -> list[Event]:
        """Follow which zone each axis is in (-1 / 0 / +1) from the size of every look pulse.

        The pill is AC-coupled: it only reports movement, never position. A held look fades within a
        second, so the return to centre reads as a fresh, full-size look the other way (measured: look
        right 145, return 139, 2.2 s later), and a direct side-to-side sweep is a pulse twice as big.
        Counting units fixes both: a pulse of one unit moves one zone, a pulse of two units moves two.
          centre -> side              report the look
          side -> centre              the eyes came back: not reported
          side -> other side (sweep)  report the look in the new direction
        A look only counts when it lands on a side. After look_return_hold_ms without a look the zone
        resets to centre, so a missed return can't swallow looks forever.
        """
        if self.return_hold_ms <= 0:
            return events
        out: list[Event] = []
        seen: list[tuple[Detection, int]] = []
        for e in events:
            axis = LOOK_AXIS.get(e.gesture) if isinstance(e, Detection) else None
            if axis is None:
                out.append(e)
                continue
            name, sign = axis
            pos, ts = self.position[name]
            seen.append((e, pos if e.ts - ts <= self.axis_hold[name] else 0))
            if e.ts - ts > self.axis_hold[name]:
                pos = 0
            if self.up_needs_swing and name == "v":
                if e.gesture == "look_up" and e.confirmed and e.swing >= self.up_swing_ratio * e.peak:
                    # Positive pulse with a PROPORTIONAL negative swing (measured 35-50% of the pulse; a
                    # return's tail is ~20%) is a real look up wherever the zone says we are. Re-syncs it.
                    self.position[name] = (1, e.ts)
                    self.last_up_ts = e.ts
                    out.append(e)
                    continue
                if e.gesture == "look_down" and 0 <= e.ts - self.last_up_ts <= self.up_bounce_ms:
                    continue  # the dip right after an up look is part of the up (measured 0.6 s later)
            if pos == 0 and not e.confirmed:
                continue  # a lone pulse from centre: noise or the return from a look we missed, not a look
            units = 2 if e.peak >= self.sweep_ratio[name] * self.direction_units[e.gesture] else 1
            new = max(-1, min(1, pos + sign * units))
            if new == pos and e.ts - ts <= self.repeat_guard_ms[name]:
                continue  # the same look again, moments later, with no return between: the bounce, not a new look
            self.position[name] = (new, e.ts)
            if new != 0:
                out.append(e)
        if seen and log.isEnabledFor(logging.INFO):
            kept = {id(x) for x in out}
            for e, pos in seen:
                log.info(
                    "%-9s peak=%4.0f swing=%3.0f conf=%d zone_before=%+d -> %s",
                    e.gesture, e.peak, e.swing, e.confirmed, pos, "KEPT" if id(e) in kept else "dropped",
                )
        return out
