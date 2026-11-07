"""Synthetic EXG — everything works with no hardware.

Two layers:

1. SyntheticEXG — raw samples in the exact format the Arduino prints (t_us, a0, a1, a2 as 10-bit
   ADC counts; A0 = horizontal EOG, A1 = vertical EOG/blinks, A2 = jaw EMG), with ground-truth
   labels. Baseline drift, 60 Hz pickup and white noise are always on; gestures add EOG steps,
   blink spikes and broadband EMG bursts (with a little crosstalk onto the other channels).
   Use it to test filters/detectors, drive the live plotter, or record labelled CSVs.

2. SyntheticSource.events() — the stream run.py sends to the backend. Until the real detectors
   (detectors.py) exist, a simulated detector decides whether each gesture is caught, from the
   signal's gain: at full strength ~97% are detected, at degrade(…, 0.3) only ~25%, and weaker
   signals false-trigger more at rest. Every outcome feeds ReliabilityTracker, so reliability
   falls because gestures are actually being missed, not because a number was set.

degrade(signal, factor) scales the gesture amplitude for that signal ("eog_h", "blink", "jaw";
"eye" = eog_h + blink) while the noise stays the same: a fading signal, not a quieter channel.
"""

import asyncio
import itertools
import math
from collections.abc import AsyncIterator
from dataclasses import dataclass

import numpy as np

import messages
from config import SIGNAL, SYNTHETIC
from reliability import ReliabilityTracker

CHANNELS = ("eog_h", "eog_v", "jaw")  # A0, A1, A2
SIGNAL_CHANNEL = {"eog_h": 0, "eog_v": 1, "blink": 1, "jaw": 2}
GESTURE_SIGNAL = {
    "look_left": "eog_h",
    "look_right": "eog_h",
    "blink_double": "blink",
    "jaw_clench": "jaw",
    "jaw_hold": "jaw",
}
GESTURE_SECONDS = {"look_left": 0.75, "look_right": 0.75, "blink_double": 0.65, "jaw_clench": 0.4, "jaw_hold": 2.5}
DEMO_SIGNALS = ["eog_h", "blink", "jaw"]
# Eye gestures dominate, as when someone is actively using eye control; HELP (jaw_hold) is never scripted.
DEFAULT_SCRIPT = ["look_left", "blink_double", "look_right", "jaw_clench", "blink_double", "look_left", "look_right"]


def degrade_targets(signal: str) -> list[str]:
    return ["eog_h", "blink"] if signal == "eye" else [signal]


@dataclass
class Label:
    gesture: str
    start_us: int
    end_us: int


class SyntheticEXG:
    """Stateful generator: call chunk(n) repeatedly for a continuous stream."""

    def __init__(self, fs: int = SIGNAL["sample_rate_hz"], seed: int | None = None, cfg: dict = SYNTHETIC) -> None:
        self.fs = fs
        self.cfg = cfg
        self.rng = np.random.default_rng(seed)
        self.n = 0  # samples generated so far
        self.gain = {s: 1.0 for s in SIGNAL_CHANNEL}
        self.labels: list[Label] = []
        self._drift_phase = self.rng.uniform(0, 2 * math.pi, size=3)

    @property
    def t_us(self) -> int:
        return round(self.n * 1e6 / self.fs)

    def degrade(self, signal: str, factor: float) -> None:
        for s in degrade_targets(signal):
            self.gain[s] = factor

    def trigger(self, gesture: str, delay_s: float = 0.0) -> Label:
        start = self.t_us + round(delay_s * 1e6)
        label = Label(gesture, start, start + round(GESTURE_SECONDS[gesture] * 1e6))
        self.labels.append(label)
        return label

    def chunk(self, n: int) -> np.ndarray:
        """n rows of (t_us, a0, a1, a2) as int64, same as the Arduino CSV."""
        idx = np.arange(self.n, self.n + n)
        t = idx / self.fs
        c = self.cfg
        x = np.zeros((3, n))
        # Always-on background: slow drift (different per channel), 60 Hz pickup, white noise.
        for ch in range(3):
            x[ch] += c["drift"] * np.sin(2 * math.pi * 0.05 * t + self._drift_phase[ch])
        x += c["mains"] * np.sin(2 * math.pi * 60.0 * t)
        x += self.rng.normal(0, c["noise"], size=(3, n))

        t_us = np.round(t * 1e6).astype(np.int64)
        for lab in self.labels:
            if lab.end_us < t_us[0] or lab.start_us > t_us[-1]:
                continue
            dt = (t_us - lab.start_us) / 1e6
            x += self._gesture(lab.gesture, dt)

        self.n += n
        adc = np.clip(np.round(x + c["adc_mid"]), 0, 1023).astype(np.int64)
        return np.column_stack([t_us, adc.T])

    def _gesture(self, gesture: str, dt: np.ndarray) -> np.ndarray:
        """Contribution of one gesture at times dt (s since onset; outside [0, dur] → 0)."""
        c, out = self.cfg, np.zeros((3, dt.size))
        dur = GESTURE_SECONDS[gesture]
        inside = (dt >= 0) & (dt <= dur)
        if gesture in ("look_left", "look_right"):
            ramp = 0.05
            shape = np.clip(np.minimum(dt, dur - dt) / ramp, 0, 1)  # trapezoid step
            sign = -1 if gesture == "look_left" else 1
            out[0] = sign * c["saccade"] * self.gain["eog_h"] * shape
        elif gesture == "blink_double":
            for onset in (0.0, 0.35):
                d = dt - onset
                spike = np.where((d >= 0) & (d <= 0.25), np.sin(math.pi * np.clip(d, 0, 0.25) / 0.25), 0)
                out[1] += c["blink"] * self.gain["blink"] * spike
                out[0] += 0.1 * c["blink"] * self.gain["blink"] * spike  # crosstalk
        elif gesture in ("jaw_clench", "jaw_hold"):
            env = np.clip(np.minimum(dt, dur - dt) / 0.02, 0, 1)
            burst = self.rng.normal(0, 1, size=dt.size) * env * c["emg"] * self.gain["jaw"]
            out[2] = burst
            out[0] += 0.15 * burst  # jaw EMG leaks onto the eye electrodes
            out[1] += 0.15 * burst
        return out * inside


class SimulatedDetector:
    """Stand-in for detectors.py: detection odds follow the signal's gain."""

    def __init__(self, rng: np.random.Generator) -> None:
        self.rng = rng

    @staticmethod
    def p_detect(gain: float) -> float:
        return float(np.clip(1.15 * gain - 0.1, 0.0, 0.97))

    @staticmethod
    def p_false_trigger(gain: float) -> float:
        return 0.01 + 0.06 * (1.0 - min(gain, 1.0))

    def detects(self, gain: float) -> bool:
        return bool(self.rng.random() < self.p_detect(gain))

    def false_triggers(self, gain: float) -> bool:
        return bool(self.rng.random() < self.p_false_trigger(gain))

    def confidence(self, gain: float) -> float:
        return float(np.clip(0.55 + 0.4 * gain + self.rng.normal(0, 0.03), 0.0, 1.0))


class SyntheticSource:
    """Gesture + reliability events for run.py. Scripted gestures and/or trigger() from the keyboard."""

    def __init__(
        self,
        interval_s: float = 0.6,
        script: list[str] | None = DEFAULT_SCRIPT,
        seed: int | None = None,
        quiet: bool = False,
    ) -> None:
        self.interval_s = interval_s
        self.script = script
        # quiet: scripted attempts and rest false triggers still move reliability (so degrade works),
        # but only trigger() gestures are sent, so a keyboard demo isn't driven by the script.
        self.quiet = quiet
        self.rng = np.random.default_rng(seed)
        self.exg = SyntheticEXG(seed=seed)  # shares gains; available for plotting/recording
        self.detector = SimulatedDetector(self.rng)
        self.tracker = ReliabilityTracker()
        for s in DEMO_SIGNALS:
            self.tracker.seed(s, accuracy=0.97, false_trigger_rate=0.02)
        self._queue: asyncio.Queue[str] = asyncio.Queue()

    @property
    def gain(self) -> dict[str, float]:
        return self.exg.gain

    def degrade(self, signal: str, factor: float) -> None:
        self.exg.degrade(signal, factor)

    def trigger(self, gesture: str) -> None:
        """Queue a gesture now (keyboard input)."""
        self._queue.put_nowait(gesture)

    def attempt(self, gesture: str, ts: int | None = None) -> dict | None:
        """One attempt at a gesture: updates reliability, returns the event if detected."""
        signal = GESTURE_SIGNAL[gesture]
        gain = self.gain[signal]
        detected = self.detector.detects(gain)
        self.tracker.record_attempt(signal, detected)
        if not detected:
            return None
        return messages.gesture(signal, gesture, self.detector.confidence(gain), ts)

    def rest_second(self) -> list[dict]:
        """One second of rest for every signal: may produce false triggers."""
        events = []
        for signal in DEMO_SIGNALS:
            gain = self.gain[signal]
            fired = self.detector.false_triggers(gain)
            self.tracker.record_rest(signal, fired)
            if fired:
                gesture = {"eog_h": "look_right", "blink": "blink_double", "jaw": "jaw_clench"}[signal]
                events.append(messages.gesture(signal, gesture, self.detector.confidence(gain) * 0.8))
        return events

    def reliability(self) -> dict:
        return messages.reliability(self.tracker.snapshot(DEMO_SIGNALS))

    async def events(self) -> AsyncIterator[dict]:
        loop = asyncio.get_running_loop()
        script = itertools.cycle(self.script) if self.script else None
        rel_every = SIGNAL["reliability_interval_ms"] / 1000
        next_gesture = loop.time() + self.interval_s
        next_rel = next_rest = loop.time() + rel_every
        while True:
            now = loop.time()
            wake = min(next_rel, next_rest, next_gesture if script else math.inf)
            try:
                gesture = await asyncio.wait_for(self._queue.get(), max(0.0, wake - now))
                if ev := self.attempt(gesture):
                    yield ev
                continue
            except asyncio.TimeoutError:
                pass
            now = loop.time()
            if script and now >= next_gesture:
                next_gesture += self.interval_s
                if (ev := self.attempt(next(script))) and not self.quiet:
                    yield ev
            if now >= next_rest:
                next_rest += 1.0
                for ev in self.rest_second():
                    if not self.quiet:
                        yield ev
            if now >= next_rel:
                next_rel += rel_every
                yield self.reliability()
