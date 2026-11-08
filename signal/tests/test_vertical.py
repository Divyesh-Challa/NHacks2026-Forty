"""A1: a look up/down is a short pulse like a blink. Told apart by shape, not by how long it is held.

Blink = positive spike then a deep negative trough (measured: about +370 then -300).
Look up = positive pulse, small trough.  Look down = negative pulse with no spike before it.
"""

import numpy as np

from detectors import Detection, Pipeline

FS = 500


def gestures(a1: np.ndarray, common_mode: bool = False) -> list[tuple[str, str]]:
    n = len(a1)
    if common_mode:
        rows = np.column_stack([np.arange(n) * 2000, a1, a1])
    else:
        rows = np.column_stack([np.arange(n) * 2000, 512 - (a1 - 512) / 2, 512 + (a1 - 512) / 2])
    p, events = Pipeline(), []
    for i in range(0, n, 50):
        events += p.process(rows[i : i + 50])
    return [(e.source, e.gesture) for e in events if isinstance(e, Detection)]


def test_short_pulse_up_and_down_are_looks() -> None:
    assert gestures(trace((3, 0.15, 300))) == [("eog_v", "look_up")]
    assert gestures(trace((3, 0.15, -250))) == [("eog_v", "look_down")]


def test_single_blink_is_not_a_look() -> None:
    assert gestures(trace(*blink(3))) == []


def test_double_blink_is_not_a_look() -> None:
    x = pulse(3, 0.15, 350) + pulse(3.4, 0.15, 350) - 512
    assert gestures(x, common_mode=True) == [("blink", "blink_double")]
