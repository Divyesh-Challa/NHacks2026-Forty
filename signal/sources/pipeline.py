"""Live source over raw samples: stream → filters → detectors → reliability → backend messages.

Used for the Arduino (SerialStream) and for synthetic waveforms run through the *real* detectors
(`run.py --source synthetic --detectors real`), so the hardware code path can be exercised with
no hardware.

Thresholds come from signal/calibration.json if calibration.py has run, else [detectors] defaults.
Live reliability (no ground truth outside calibration):
  - a detection counts as a successful attempt; a near-miss (past the floor, short of threshold)
    counts as a failed one — so a fading signal loses reliability as the user keeps trying
  - false-trigger rate stays at its calibrated value (the backend can feed usage errors later)
"""

import asyncio
import itertools
from collections.abc import AsyncIterator

import messages
from calibration import load_calibration
from config import SIGNAL
from detectors import Detection, Pipeline
from reliability import ReliabilityTracker

SIGNALS = ["eog_h", "eog_v", "blink"]
POLL_S = 0.02


class PipelineSource:
    def __init__(self, stream, script: list[str] | None = None, interval_s: float = 2.0, calibration: dict | None = None) -> None:
        self.stream = stream
        cal = calibration if calibration is not None else load_calibration()
        self.pipeline = Pipeline(settings=(cal or {}).get("settings"))
        self.tracker = ReliabilityTracker()
        for sig in SIGNALS:
            r = (cal or {}).get("signals", {}).get(sig)
            if r:
                self.tracker.seed(sig, r["accuracy"], r["false_trigger_rate"])
            else:
                self.tracker.seed(sig, self.tracker.default_accuracy, self.tracker.default_false_trigger_rate)
        self.script = script
        self.interval_s = interval_s
        self.calibrated = bool(cal)

    @property
    def exg(self):
        """The synthetic generator, when the stream is synthetic (None for real hardware)."""
        return getattr(self.stream, "exg", None)

    def degrade(self, signal: str, factor: float) -> None:
        if self.exg is not None:
            self.exg.degrade(signal, factor)  # synthetic: shrink the gesture, keep the noise
            self.pipeline.mark_degraded(signal, factor < 1)
        else:
            self.pipeline.set_gain(signal, factor)  # hardware: scale the measured signal

    def trigger(self, gesture: str) -> None:
        if self.exg is not None:
            self.exg.trigger(gesture)

    def handle(self, rows) -> list[dict]:
        out = []
        for ev in self.pipeline.process(rows):
            self.tracker.record_attempt(ev.source, isinstance(ev, Detection))
            if isinstance(ev, Detection):
                out.append(messages.gesture(ev.source, ev.gesture, ev.confidence))
        return out

    def reliability(self) -> dict:
        return messages.reliability(self.tracker.snapshot(SIGNALS))

    async def events(self) -> AsyncIterator[dict]:
        loop = asyncio.get_running_loop()
        script = itertools.cycle(self.script) if self.script and self.exg is not None else None
        rel_every = SIGNAL["reliability_interval_ms"] / 1000
        next_rel = loop.time() + rel_every
        next_gesture = loop.time() + self.interval_s
        while True:
            await asyncio.sleep(POLL_S)
            now = loop.time()
            if script and now >= next_gesture:
                next_gesture += self.interval_s
                self.exg.trigger(next(script))
            for ev in self.handle(self.stream.read()):
                yield ev
            if now >= next_rel:
                next_rel += rel_every
                yield self.reliability()
