"""Detectors on synthetic waveforms: every gesture detected, no extras, near-misses."""

import numpy as np

from detectors import BlinkDetector, Detection, NearMiss, Pipeline, confidence
from sources.synthetic import SyntheticEXG

FS = 500


def run(gestures: list[str], gap_s: float = 3.5, seed: int = 0, gain: dict | None = None, chunk: int = 10) -> list:
    exg = SyntheticEXG(seed=seed)
    for sig, g in (gain or {}).items():
        exg.degrade(sig, g)
    t = 1.0
    for g in gestures:
        exg.trigger(g, delay_s=t)
        t += gap_s
    rows = exg.chunk(int(FS * (t + 3.0)))
    p = Pipeline()
    events = []
    for i in range(0, len(rows), chunk):  # stream it the way the live source does
        events += p.process(rows[i : i + chunk])
    return events


def names(events: list) -> list[str]:
    return [e.gesture if isinstance(e, Detection) else f"miss:{e.source}" for e in events]


ALL = ["look_left", "look_right", "blink_double", "look_up", "look_right", "look_left"]


def test_every_gesture_detected_once_in_order() -> None:
    for seed in range(5):
        assert names(run(ALL, seed=seed)) == ALL


def test_confidence_scales_with_signal_strength() -> None:
    strong = [e.confidence for e in run(["look_left"] * 3) if isinstance(e, Detection)]
    weak = [e.confidence for e in run(["look_left"] * 3, gain={"eog_h": 0.65}) if isinstance(e, Detection)]
    assert min(strong) > 0.9 and max(weak) < 0.8
    assert confidence(80, 80) == 0.5 and confidence(160, 80) == 1.0


def test_rest_produces_nothing() -> None:
    exg = SyntheticEXG(seed=4)
    assert Pipeline().process(exg.chunk(60 * FS)) == []  # a minute of drift, mains and noise


def test_look_and_return_does_not_fire_the_opposite_direction() -> None:
    # A 0.75 s look then back to centre: one look_left, no look_right from the return.
    assert names(run(["look_left"] * 4, gap_s=2.0)) == ["look_left"] * 4


def test_help_hold_emits_blink_hold_once() -> None:
    events = run(["blink_hold"])
    assert names(events) == ["blink_hold"]
    hold = events[0]
    assert 1000 + 2000 <= hold.ts <= 1000 + 2600


def test_short_blink_is_never_help() -> None:
    assert names(run(["blink_double"] * 3)) == ["blink_double"] * 3


def test_single_blink_is_ignored() -> None:
    det = BlinkDetector()
    t = np.arange(2 * FS) * 2000
    x = np.full(t.size, 512.0)
    x[FS // 2 : FS // 2 + 100] += 200 * np.sin(np.pi * np.arange(100) / 100)
    assert det.process(x, t) == []


def test_degraded_gestures_become_near_misses() -> None:
    events = run(["look_left", "look_right", "blink_double"], gain={"eog_h": 0.3, "blink": 0.3})
    assert names(events) == ["miss:eog_h", "miss:eog_h", "miss:blink"]
    assert all(isinstance(e, NearMiss) for e in events)


def test_hardware_gain_knob_degrades_like_a_weak_signal() -> None:
    exg = SyntheticEXG(seed=1)
    exg.trigger("look_left", delay_s=1.0)
    rows = exg.chunk(3 * FS)
    p = Pipeline()
    p.set_gain("eye", 0.3)
    assert names(p.process(rows)) == ["miss:eog_h"]
