"""Calibration: thresholds adapt to the person, accuracy numbers, polarity, live source seeding."""

import numpy as np

from calibration import _onset, calibrate, segments, synthetic_session
from sources.pipeline import PipelineSource
from sources.synthetic import SyntheticEXG


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def read(self):
        r, self.rows = self.rows, self.rows[:0]
        return r


def test_segments() -> None:
    t = np.arange(6)
    assert segments(t, ["rest", "rest", "look_left", "look_left", "rest", "rest"]) == [
        ("rest", 0, 1), ("look_left", 2, 3), ("rest", 4, 5)
    ]


def test_synthetic_calibration_is_accurate_with_no_false_triggers() -> None:
    result = calibrate(*synthetic_session(reps=6, seed=1))
    for sig in ("eog_h", "blink"):
        r = result["signals"][sig]
        assert r["accuracy"] >= 0.9 and r["false_trigger_rate"] <= 0.05, (sig, r)
    assert result["signals"]["eog_h"]["attempts"] == 12  # left + right
    assert result["settings"]["eog_invert"] is False


def test_thresholds_follow_the_persons_amplitude() -> None:
    strong = calibrate(*synthetic_session(reps=4, seed=2))["settings"]
    weak = calibrate(*synthetic_session(reps=4, seed=2, gain={"eog_h": 0.5}))["settings"]
    assert weak["eog_threshold"] < 0.7 * strong["eog_threshold"]
    assert weak["eog_floor"] < weak["eog_threshold"]


def test_inverted_electrodes_are_detected() -> None:
    rows, labels = synthetic_session(reps=4, seed=3)
    flipped = rows.copy()
    flipped[:, 1] = 1024 - flipped[:, 1]  # electrodes swapped: left reads positive
    result = calibrate(flipped, labels)
    assert result["settings"]["eog_invert"] is True
    assert result["signals"]["eog_h"]["accuracy"] >= 0.9


def test_polarity_comes_from_the_look_not_its_larger_return() -> None:
    # AC-coupled pill: look left (negative pulse), then the return to centre reads as a bigger positive one.
    t = np.arange(1000) / 500
    d = -100 * np.exp(-(((t - 0.4) / 0.08) ** 2)) + 120 * np.exp(-(((t - 1.2) / 0.08) ** 2))
    assert _onset(d) < 0 and abs(_onset(d)) > 115


def test_live_source_uses_calibration_and_near_misses_lower_reliability() -> None:
    cal = calibrate(*synthetic_session(reps=4, seed=4))
    exg = SyntheticEXG(seed=5)
    exg.degrade("eye", 0.3)
    for i in range(8):
        exg.trigger("look_left" if i % 2 else "look_right", delay_s=1.0 + 2.0 * i)
    src = PipelineSource(Rows(exg.chunk(19 * 500)), calibration=cal)
    assert src.reliability()["signals"]["eog_h"] >= 0.9  # seeded from calibration
    assert src.handle(src.stream.read()) == []  # weak looks aren't detected...
    assert src.reliability()["signals"]["eog_h"] < 0.6  # ...and the near-misses count against it


class SyntheticRows:
    """A synthetic stream that hands out `seconds` of samples per read (PipelineSource drives exg)."""

    def __init__(self, seconds: float, seed: int) -> None:
        self.exg = SyntheticEXG(seed=seed)
        self.n = int(seconds * 500)

    def read(self):
        return self.exg.chunk(self.n)


def test_eye_degrade_lowers_both_eye_signals_through_the_real_detectors() -> None:
    """run.py --detectors real: an "eye" degrade must take eog_v down with eog_h (the wheel needs both)."""
    src = PipelineSource(SyntheticRows(2.0, seed=6), calibration=calibrate(*synthetic_session(reps=4, seed=4)))
    first = src.reliability()["signals"]
    assert set(first) == {"eog_h", "eog_v", "blink"}
    src.degrade("eye", 0.3)
    for g in ["look_left", "look_up", "look_right", "look_down", "blink_double"] * 4:
        src.trigger(g)
        src.handle(src.stream.read())
    r = src.reliability()["signals"]
    assert r["eog_h"] < 0.6 and r["eog_v"] < 0.6
    assert r["blink"] >= 0.75
    src.degrade("eye", 1.0)
    assert not src.pipeline.vert.misses
