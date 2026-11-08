"""A1: a look up/down is a short pulse like a blink. Told apart by shape, not by how long it is held.

Blink = positive spike then a deep negative trough (measured: about +370 then -300).
Look up = positive pulse, small trough.  Look down = negative pulse with no spike before it.
"""

import numpy as np

from detectors import Detection, Pipeline

FS = 500


def trace(*pulses: tuple[float, float, float]) -> np.ndarray:
    """A1 baseline 512 with rectangular (start_s, dur_s, amp) pulses."""
    x = np.full(8 * FS, 512.0)
    for start, dur, amp in pulses:
        x[int(start * FS) : int((start + dur) * FS)] += amp
    return x


def blink(at: float) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    return (at, 0.12, 350), (at + 0.12, 0.15, -300)  # spike, then trough


def gestures(a1: np.ndarray) -> list[tuple[str, str]]:
    n = len(a1)
    rows = np.column_stack([np.arange(n) * 2000, np.full(n, 512), a1, np.full(n, 500)])
    p, events = Pipeline(), []
    for i in range(0, n, 50):
        events += p.process(rows[i : i + 50])
    return [(e.source, e.gesture) for e in events if isinstance(e, Detection)]


def test_short_pulse_up_and_down_are_looks() -> None:
    assert gestures(trace((3, 0.15, 300))) == [("eog_v", "look_up")]
    assert gestures(trace((3, 0.15, -250))) == [("eog_v", "look_down")]


def test_single_blink_is_not_a_look() -> None:
    assert gestures(trace(*blink(3))) == []


def test_double_blink_is_a_blink_not_looks() -> None:
    assert gestures(trace(*blink(3), *blink(3.4))) == [("blink", "blink_double")]


def test_deep_trough_after_a_spike_makes_it_a_blink_not_a_look() -> None:
    assert gestures(trace((3, 0.15, 300), (3.5, 0.2, -200))) == []


def test_rebound_after_a_look_is_not_the_opposite_look() -> None:
    assert gestures(trace((3, 0.15, 300), (3.6, 0.2, -130))) == [("eog_v", "look_up")]  # small trough
    assert gestures(trace((3, 0.15, -250), (5.0, 0.15, 150))) == [("eog_v", "look_down")]  # rebound 1.9 s later
