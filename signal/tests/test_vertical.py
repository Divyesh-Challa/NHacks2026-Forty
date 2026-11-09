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


def test_a_blink_under_a_hardware_eye_degrade_is_still_a_blink_not_a_look() -> None:
    # The gain knob scales the pulse, so the blink-sized test has to scale with it, or every rest
    # blink reads as a successful look up and eog_v never falls.
    a1 = trace(*blink(3))
    n = len(a1)
    rows = np.column_stack([np.arange(n) * 2000, np.full(n, 512), a1, np.full(n, 500)])
    p = Pipeline(settings={"vert_threshold": 26.0, "vert_floor": 13.0, "vert_invert": False})
    p.set_gain("eye", 0.3)
    events = []
    for i in range(0, n, 50):
        events += p.process(rows[i : i + 50])
    assert [e for e in events if e.source == "eog_v"] == []


def test_short_pulse_up_and_down_are_looks() -> None:
    assert gestures(trace((3, 0.15, 300))) == [("eog_v", "look_up")]
    assert gestures(trace((3, 0.15, -250))) == [("eog_v", "look_down")]


def test_single_blink_is_not_a_look() -> None:
    assert gestures(trace(*blink(3))) == []


def test_double_blink_is_a_blink_not_looks() -> None:
    assert gestures(trace(*blink(3), *blink(3.4))) == [("blink", "blink_double")]


def test_deep_trough_after_a_spike_makes_it_a_blink_not_a_look() -> None:
    assert gestures(trace((3, 0.15, 300), (3.5, 0.2, -200))) == []


def test_small_look_up_with_an_equally_small_negative_swing_is_still_a_look() -> None:
    # Measured on hardware (earlobe reference): look up = +60 then -45 about 100 ms later. A blink is
    # +180..+320 with a -400 trough, so the small pair must not be mistaken for a blink trough.
    rows_a1 = trace((3, 0.1, 60), (3.12, 0.15, -45))
    n = len(rows_a1)
    rows = np.column_stack([np.arange(n) * 2000, np.full(n, 512), rows_a1, np.full(n, 500)])
    p = Pipeline(settings={"vert_threshold": 26.0, "vert_floor": 13.0, "vert_invert": False})
    events = []
    for i in range(0, n, 50):
        events += p.process(rows[i : i + 50])
    assert [(e.source, e.gesture) for e in events if isinstance(e, Detection)] == [("eog_v", "look_up")]


def test_bounce_after_a_look_up_does_not_fire_a_second_look_up() -> None:
    # Hardware: after a look up the return-to-centre bounce is a negative swing, then a small positive
    # pulse (~28, just over the threshold) about 1.5 s later. That must not become a second look up
    # (on the wheel a second up means "go back").
    a1 = trace((3, 0.1, 60), (3.12, 0.15, -45), (4.45, 0.08, -32), (4.55, 0.09, 30))
    n = len(a1)
    rows = np.column_stack([np.arange(n) * 2000, np.full(n, 512), a1, np.full(n, 500)])
    p = Pipeline(settings={"vert_threshold": 26.0, "vert_floor": 13.0, "vert_invert": False})
    events = []
    for i in range(0, n, 50):
        events += p.process(rows[i : i + 50])
    assert [(e.source, e.gesture) for e in events if isinstance(e, Detection)] == [("eog_v", "look_up")]


RIG = {  # measured on the earlobe-reference rig: up = +80..110 then -35..-75; return from down = lone +60..95
    "vert_threshold": 30.0,
    "vert_floor": 15.0,
    "vert_invert": False,
    "vert_rearm_ms": 0,
    "vert_up_trough_ratio": 0.2,
    "blink_unit": 162.0,
}


def rig_gestures(a1: np.ndarray) -> list[tuple[str, str]]:
    n = len(a1)
    rows = np.column_stack([np.arange(n) * 2000, np.full(n, 512), a1, np.full(n, 500)])
    p, events = Pipeline(settings=RIG), []
    for i in range(0, n, 50):
        events += p.process(rows[i : i + 50])
    return [(e.source, e.gesture) for e in events if isinstance(e, Detection) and e.source == "eog_v"]


def test_up_look_needs_its_negative_swing_on_a_biphasic_rig() -> None:
    assert rig_gestures(trace((3, 0.1, 90), (3.12, 0.2, -50))) == [("eog_v", "look_up")]
    # A lone positive pulse is the return from a look down, not a look up.
    assert rig_gestures(trace((3, 0.1, 80))) == []


def test_a_tiny_twitch_before_a_weak_down_does_not_hide_the_down() -> None:
    # Measured: +24 (under the threshold), then -31 a few ms later was a real look down.
    assert rig_gestures(trace((3, 0.04, 24), (3.045, 0.13, -34))) == [("eog_v", "look_down")]


def test_up_look_with_a_small_negative_swing_still_counts() -> None:
    # Measured on the rig: some up looks only swing -22..-26 behind a +90 pulse.
    assert rig_gestures(trace((3, 0.1, 90), (3.12, 0.2, -23))) == [("eog_v", "look_up")]


def test_blink_sized_spike_with_a_modest_trough_is_a_blink_not_a_look_up() -> None:
    # Measured: +240 then -111 (46% of the spike) was reported as look up. Only blinks are that big.
    assert rig_gestures(trace((3, 0.12, 240), (3.14, 0.2, -111))) == []


def test_the_small_tail_after_a_return_does_not_make_it_a_look_up() -> None:
    # Return from a look down: +82 then a small tail. Raw -8 measures ~15-16 after filtering (the real
    # tails); a look up's swing measures 22-75.
    assert rig_gestures(trace((3, 0.1, 80), (3.12, 0.2, -8))) == []


def test_down_then_its_return_is_one_look_down_and_nothing_else() -> None:
    assert rig_gestures(trace((3, 0.1, -55), (5.6, 0.12, 85))) == [("eog_v", "look_down")]


def test_up_look_is_not_mistaken_for_a_blink_when_the_blink_threshold_is_low() -> None:
    # blink_threshold 81 made the old "75% of it" rule treat a 90-high up pulse as a blink spike.
    assert rig_gestures(trace((3, 0.1, 100), (3.12, 0.2, -70))) == [("eog_v", "look_up")]


def test_real_blink_is_still_not_a_look_on_the_rig() -> None:
    assert rig_gestures(trace(*blink(3))) == []


def test_next_look_right_after_a_return_is_not_swallowed_by_a_rearm_window() -> None:
    # down, its return (dropped), then an up soon after: the old 2.5 s rearm blocked this.
    a1 = trace((2, 0.1, -55), (4.6, 0.12, 85), (6.0, 0.1, 90), (6.12, 0.2, -50))
    assert rig_gestures(a1) == [("eog_v", "look_down"), ("eog_v", "look_up")]


def test_rebound_after_a_look_is_not_the_opposite_look() -> None:
    assert gestures(trace((3, 0.15, 300), (3.6, 0.2, -130))) == [("eog_v", "look_up")]  # small trough
    assert gestures(trace((3, 0.15, -250), (5.0, 0.15, 150))) == [("eog_v", "look_down")]  # rebound 1.9 s later


def test_a_confirmed_up_counts_even_if_the_zone_thinks_we_are_already_down() -> None:
    # Missed return from the previous down left the tracker in the down zone; the real up (pulse + swing) must still fire.
    a1 = trace((1, 0.1, -55), (4.0, 0.1, 90), (4.12, 0.2, -30))
    assert rig_gestures(a1) == [("eog_v", "look_down"), ("eog_v", "look_up")]


def test_two_real_ups_in_a_row_both_fire() -> None:
    a1 = trace((1, 0.1, 90), (1.12, 0.2, -30), (2.5, 0.1, 90), (2.62, 0.2, -30))
    assert rig_gestures(a1) == [("eog_v", "look_up"), ("eog_v", "look_up")]


def test_dip_shortly_after_an_up_is_not_a_look_down() -> None:
    a1 = trace((1, 0.1, 90), (1.12, 0.2, -30), (1.8, 0.1, -60))
    assert rig_gestures(a1) == [("eog_v", "look_up")]


def test_return_from_down_with_a_small_tail_is_not_a_look_up() -> None:
    # Measured: return +109 then a -25 trough (23% of the pulse). A real up's swing is 35-50%.
    a1 = trace((1, 0.1, -60), (3.5, 0.13, 105), (3.7, 0.11, -18))
    assert rig_gestures(a1) == [("eog_v", "look_down")]


def test_return_dip_two_seconds_after_an_up_still_resets_the_zone() -> None:
    # The dip 1.8 s after an up is the return; if it were treated as a bounce the next real down would be swallowed.
    a1 = trace((1, 0.1, 90), (1.12, 0.2, -35), (2.9, 0.1, -50), (5.0, 0.1, -60))
    assert rig_gestures(a1) == [("eog_v", "look_up"), ("eog_v", "look_down")]
