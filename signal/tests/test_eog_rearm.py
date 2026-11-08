"""Coming back to centre after a held look must not read as a look the other way.

The EXG pill is AC-coupled, so a held look fades and the return overshoots. Modelled here as a
first-order high-pass (tau 1 s) on an eye-position step held for 1.5 s.
"""

import numpy as np

from detectors import Detection, Pipeline

FS = 500


def ac_coupled_look(direction: int, amp: float = 350.0, tau_s: float = 1.0) -> np.ndarray:
    pos = np.zeros(8 * FS)
    pos[2 * FS : int(3.5 * FS)] = direction * amp  # look at 2.0 s, back to centre at 3.5 s
    a = tau_s / (tau_s + 1 / FS)
    y, prev = np.zeros_like(pos), 0.0
    for i in range(1, len(pos)):
        y[i] = a * (y[i - 1] + pos[i] - pos[i - 1])
    return 512.0 + y


def gestures(a0: np.ndarray) -> list[str]:
    n = len(a0)
    rows = np.column_stack([np.arange(n) * 2000, a0, np.full(n, 512), np.full(n, 500)])
    p, events = Pipeline(settings={"eog_threshold": 189.0, "eog_floor": 96.0}), []
    for i in range(0, n, 50):
        events += p.process(rows[i : i + 50])
    return [e.gesture for e in events if isinstance(e, Detection) and e.source == "eog_h"]


def test_return_to_centre_is_not_the_opposite_look() -> None:
    assert gestures(ac_coupled_look(+1)) == ["look_right"]
    assert gestures(ac_coupled_look(-1)) == ["look_left"]
