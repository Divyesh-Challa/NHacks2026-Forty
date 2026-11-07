"""A1 look up/down must outlast a blink; blinks must still read as blinks."""

import numpy as np

from detectors import Detection, Pipeline

FS = 500


def gestures(a1: np.ndarray) -> list[tuple[str, str]]:
    n = len(a1)
    rows = np.column_stack([np.arange(n) * 2000, np.full(n, 512), a1, np.full(n, 500)])
    p, events = Pipeline(), []
    for i in range(0, n, 50):
        events += p.process(rows[i : i + 50])
    return [(e.source, e.gesture) for e in events if isinstance(e, Detection)]


def pulse(start_s: float, dur_s: float, amp: float) -> np.ndarray:
    x = np.full(6 * FS, 512.0)
    x[int(start_s * FS) : int((start_s + dur_s) * FS)] += amp
    return x


def test_held_look_up_and_down() -> None:
    assert gestures(pulse(3, 1.0, 350)) == [("eog_v", "look_up")]
    assert gestures(pulse(3, 1.0, -350)) == [("eog_v", "look_down")]


def test_single_blink_is_not_a_look() -> None:
    assert gestures(pulse(3, 0.2, 350)) == []


def test_double_blink_is_not_a_look() -> None:
    x = pulse(3, 0.15, 350) + pulse(3.4, 0.15, 350) - 512
    assert gestures(x) == [("blink", "blink_double")]
