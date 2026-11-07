"""Synthetic source — works with no hardware. Owner: Role B.

SCAFFOLD STATUS: emits a scripted gesture sequence directly (skips waveforms) plus
periodic reliability, so the backend and UI get real traffic today.
TODO (Role B):
  - generate raw samples at SIGNAL["sample_rate_hz"]: EOG steps (look L/R), blink spikes,
    jaw EMG bursts, baseline drift, 60 Hz noise — run them through filters + detectors
  - scriptable gestures (keyboard or timed sequence)
  - degrade(signal, factor) scales amplitude so detectors miss/false-trigger realistically
"""

import asyncio
import itertools
from collections.abc import AsyncIterator

import messages

SCRIPT = [("eog_h", "look_left"), ("eog_h", "look_right"), ("jaw", "jaw_clench"), ("blink", "blink_double")]


class SyntheticSource:
    def __init__(self, interval_s: float = 2.0) -> None:
        self.interval_s = interval_s
        self.gain: dict[str, float] = {"eog_h": 1.0, "eog_v": 1.0, "blink": 1.0, "jaw": 1.0}

    def degrade(self, signal: str, factor: float) -> None:
        self.gain[signal] = factor

    async def events(self) -> AsyncIterator[dict]:
        for source, name in itertools.cycle(SCRIPT):
            await asyncio.sleep(self.interval_s)
            yield messages.gesture(source, name, 0.9 * self.gain.get(source, 1.0))
            yield messages.reliability({s: min(1.0, 0.9 * g) for s, g in self.gain.items()})
