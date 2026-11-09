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
    rows = exg.chunk(int(FS * (t + 1.5)))
    p = Pipeline()
    for sig, g in (gain or {}).items():
        p.mark_degraded(sig, g < 1)  # what PipelineSource.degrade does for a synthetic stream
    events = []
    for i in range(0, len(rows), chunk):  # stream it the way the live source does
        events += p.process(rows[i : i + chunk])
    return events


def names(events: list) -> list[str]:
    return [e.gesture if isinstance(e, Detection) else f"miss:{e.source}" for e in events]


# Opposite looks are kept > look_return_hold_ms (8 s) apart: closer than that, the second one is the eyes returning.
ALL = ["look_left", "look_left", "blink_double", "blink_double", "look_right", "look_right"]


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


def test_single_blink_is_ignored() -> None:
    det = BlinkDetector()
    t = np.arange(2 * FS) * 2000
    x = np.full(t.size, 512.0)
    x[FS // 2 : FS // 2 + 100] += 200 * np.sin(np.pi * np.arange(100) / 100)
    assert det.process(x, t) == []


def test_double_blink_with_deep_undershoot_is_detected() -> None:
    # AC-coupled pills dip far below baseline after each spike (hardware: about -400). The idle baseline
    # must not chase the dip, or the second blink opens against a lowered baseline and never closes.
    det = BlinkDetector()
    t = np.arange(9 * FS) * 2000
    x = np.full(t.size, 512.0)

    def blink(at_s: float) -> None:
        i = int(at_s * FS)
        x[i : i + 75] += 280 * np.sin(np.pi * np.arange(75) / 75)  # 150 ms spike
        x[i + 75 : i + 175] -= 380 * np.sin(np.pi * np.arange(100) / 100)  # 200 ms dip
        x[i + 175 : i + 375] -= 90 * np.exp(-np.arange(200) / 80)  # slow recovery

    blink(2.0)
    blink(2.34)
    got = [e.gesture for e in det.process(x, t) if isinstance(e, Detection)]
    assert got == ["blink_double"]


def test_blink_closes_when_resting_level_settles_just_above_the_floor() -> None:
    # After the dip the signal can plateau ~45 above the old baseline for seconds (above floor/2 = 30
    # for the default floor 40). The blink must still close, or the next blink is swallowed.
    det = BlinkDetector()
    t = np.arange(9 * FS) * 2000
    x = np.full(t.size, 512.0)
    for at_s in (2.0, 2.34):
        i = int(at_s * FS)
        x[i : i + 75] += 280 * np.sin(np.pi * np.arange(75) / 75)
    x[int(2.34 * FS) + 75 :] += 45  # settled a little above where it started
    got = [e.gesture for e in det.process(x, t) if isinstance(e, Detection)]
    assert got == ["blink_double"]


def _a1_pulse_rows(with_horizontal_look: bool) -> np.ndarray:
    """A 120 ms positive pulse on A1 (a look up on its own); optionally a left look on A0 at the same time."""
    n = 8 * FS
    rows = np.zeros((n, 4), dtype=float)
    rows[:, 0] = np.arange(n) * 2000
    rows[:, 1:] = 512.0
    i = 3 * FS
    rows[i : i + 60, 2] += 60 * np.sin(np.pi * np.arange(60) / 60)
    if with_horizontal_look:
        ramp = np.clip(np.minimum(np.arange(375), 375 - np.arange(375)) / 25, 0, 1)
        rows[i - 20 : i + 355, 1] -= 160 * ramp
    return rows


def test_a1_pulse_alone_is_a_vertical_look() -> None:
    settings = {"vert_threshold": 26.0, "vert_floor": 13.0, "vert_invert": False}
    events = Pipeline(settings=settings).process(_a1_pulse_rows(False))
    assert [e.gesture for e in events if isinstance(e, Detection)] == ["look_up"]


def test_opposite_look_soon_after_a_look_is_the_return_to_centre() -> None:
    # Look left (reported), eyes come back (the opposite pulse is NOT a look right), look right (reported).
    assert names(run(["look_left", "look_right", "look_right"])) == ["look_left", "look_right"]


def _ac_coupled(steps: list[tuple[float, float]], seconds: float = 9.0, tau_s: float = 1.0) -> np.ndarray:
    """A0 for an eye-position trace [(time_s, position)], through a first-order high-pass (the AC-coupled pill)."""
    pos = np.zeros(int(seconds * FS))
    for at, value in steps:
        pos[int(at * FS) :] = value
    a = tau_s / (tau_s + 1 / FS)
    y = np.zeros_like(pos)
    for i in range(1, len(pos)):
        y[i] = a * (y[i - 1] + pos[i] - pos[i - 1])
    return 512.0 + y


def _looks(a0: np.ndarray) -> list[str]:
    n = len(a0)
    rows = np.column_stack([np.arange(n) * 2000, a0, np.full(n, 512), np.full(n, 500)])
    p = Pipeline(settings={"eog_threshold": 100.0, "eog_floor": 50.0, "eog_rearm_ms": 0})
    events = []
    for i in range(0, n, 50):
        events += p.process(rows[i : i + 50])
    return [e.gesture for e in events if isinstance(e, Detection) and e.source == "eog_h"]


def test_side_to_side_sweep_is_a_look_in_the_new_direction() -> None:
    # centre -> left (200), then straight across to the right (+200): a 400-unit sweep, then back to centre.
    # Reported: look_left, look_right. The final return to centre (a single-size opposite pulse) is not.
    got = _looks(_ac_coupled([(2.0, -200.0), (5.0, 200.0), (8.0, 0.0)], seconds=11.0))
    assert got == ["look_left", "look_right"]


def test_return_to_centre_after_a_held_look_is_not_reported() -> None:
    assert _looks(_ac_coupled([(2.0, -200.0), (5.0, 0.0)])) == ["look_left"]


def test_opposite_look_long_after_a_look_is_a_real_look() -> None:
    assert names(run(["look_left", "look_right"], gap_s=9.0)) == ["look_left", "look_right"]


def test_vertical_detection_next_to_a_horizontal_look_is_dropped_as_crosstalk() -> None:
    settings = {"vert_threshold": 26.0, "vert_floor": 13.0, "vert_invert": False}
    events = Pipeline(settings=settings).process(_a1_pulse_rows(True))
    assert [e.gesture for e in events if isinstance(e, Detection)] == ["look_left"]


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


def test_synthetic_vertical_looks_are_detected_and_not_blinks() -> None:
    # Opposite looks on one axis are kept > look_return_hold_ms apart, as in ALL.
    got = names(run(["look_up", "blink_double", "look_down", "look_left", "look_up"], gap_s=8.0))
    assert got == ["look_up", "blink_double", "look_down", "look_left", "look_up"]


def test_degraded_vertical_looks_become_near_misses_while_degraded() -> None:
    assert names(run(["look_up", "look_down"], gap_s=8.0, gain={"eye": 0.3})) == ["miss:eog_v", "miss:eog_v"]
    # Not degraded (the rig as calibrated): the same weak pulses are dropped, never counted against eog_v.
    exg = SyntheticEXG(seed=0)
    exg.degrade("eye", 0.3)
    exg.trigger("look_up", delay_s=1.0)
    assert Pipeline().process(exg.chunk(4 * FS)) == []


def test_degraded_eye_rest_and_blinks_make_no_vertical_near_misses() -> None:
    p = Pipeline()
    p.set_gain("eye", 0.3)
    assert p.process(SyntheticEXG(seed=4).chunk(60 * FS)) == []  # a minute of rest
    events = run(["blink_double"] * 4, gap_s=3.0, gain={"eye": 0.3})
    assert names(events) == ["blink_double"] * 4


def test_hardware_gain_knob_turns_vertical_near_misses_on_and_off() -> None:
    p = Pipeline()
    p.set_gain("eye", 0.3)
    assert p.vert.misses
    p.set_gain("eye", 1.0)
    assert not p.vert.misses
    p.set_gain("blink", 0.3)
    assert not p.vert.misses


def test_a2_is_ignored() -> None:
    # Whatever is (or isn't) plugged into A2 must never produce a gesture.
    exg = SyntheticEXG(seed=3)
    rows = exg.chunk(30 * FS)
    rows[:, 3] = 512 + 400 * np.sin(np.arange(len(rows)) / 5.0)
    assert Pipeline().process(rows) == []
