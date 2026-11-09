"""Synthetic EXG: Arduino-format waveforms with labels, degrade, and the simulated event stream."""

import asyncio
import itertools

import numpy as np

from sources.synthetic import DEFAULT_SCRIPT, SimulatedDetector, SyntheticEXG, SyntheticSource

FS = 500


def window(rows: np.ndarray, start_s: float, end_s: float) -> np.ndarray:
    t = rows[:, 0] / 1e6
    return rows[(t >= start_s) & (t < end_s)]


def test_rows_match_arduino_format() -> None:
    rows = SyntheticEXG(seed=1).chunk(FS)
    assert rows.shape == (FS, 4) and rows.dtype == np.int64
    assert np.all(np.diff(rows[:, 0]) == 2000)  # 500 Hz in microseconds
    assert rows[:, 1:].min() >= 0 and rows[:, 1:].max() <= 1023
    assert abs(rows[:, 1:].mean() - 512) < 40  # centred like the BioAmp output


def test_chunks_are_continuous() -> None:
    exg = SyntheticEXG(seed=1)
    a, b = exg.chunk(100), exg.chunk(100)
    assert b[0, 0] - a[-1, 0] == 2000


def test_look_left_and_right_step_opposite_ways_on_a0() -> None:
    exg = SyntheticEXG(seed=2)
    exg.trigger("look_left", delay_s=0.5)
    exg.trigger("look_right", delay_s=2.0)
    rows = exg.chunk(FS * 3)
    rest = window(rows, 0.0, 0.4)[:, 1].mean()
    left = window(rows, 0.65, 1.1)[:, 1].mean()
    right = window(rows, 2.15, 2.6)[:, 1].mean()
    assert left < rest - 100 and right > rest + 100


def test_look_up_and_down_step_opposite_ways_on_a1() -> None:
    exg = SyntheticEXG(seed=2)
    exg.trigger("look_up", delay_s=0.5)
    exg.trigger("look_down", delay_s=2.0)
    rows = exg.chunk(FS * 3)
    rest = window(rows, 0.0, 0.4)[:, 2].mean()
    up = window(rows, 0.65, 1.1)[:, 2].mean()
    down = window(rows, 2.15, 2.6)[:, 2].mean()
    assert up > rest + 150 and down < rest - 150


def test_blink_spikes_on_a1() -> None:
    exg = SyntheticEXG(seed=3)
    exg.trigger("blink_double", delay_s=0.5)
    rows = exg.chunk(FS * 2)
    assert window(rows, 0.5, 1.2)[:, 2].max() - window(rows, 0.0, 0.4)[:, 2].mean() > 150


def test_labels_are_ground_truth() -> None:
    exg = SyntheticEXG(seed=5)
    lab = exg.trigger("look_left", delay_s=1.0)
    assert (lab.gesture, lab.start_us, lab.end_us) == ("look_left", 1_000_000, 1_750_000)


def test_degrade_shrinks_the_gesture_not_the_noise() -> None:
    def step_size(factor: float) -> float:
        exg = SyntheticEXG(seed=6)
        exg.degrade("eye", factor)
        exg.trigger("look_right", delay_s=0.5)
        rows = exg.chunk(FS * 2)
        return window(rows, 0.65, 1.1)[:, 1].mean() - window(rows, 0.0, 0.4)[:, 1].mean()

    full, weak = step_size(1.0), step_size(0.3)
    assert abs(weak / full - 0.3) < 0.1


def test_simulated_detector_tracks_gain() -> None:
    assert SimulatedDetector.p_detect(1.0) > 0.95
    assert SimulatedDetector.p_detect(0.3) < 0.3
    assert SimulatedDetector.p_false_trigger(0.3) > SimulatedDetector.p_false_trigger(1.0)


def test_degrade_makes_reliability_fall_below_cutoff_from_missed_gestures() -> None:
    src = SyntheticSource(seed=7)
    for _ in range(20):
        src.attempt("look_left")
    assert src.tracker.score("eog_h") > 0.75
    src.degrade("eye", 0.3)
    for _ in range(8):
        src.attempt("look_left")
        src.attempt("look_up")
        src.attempt("blink_double")
    assert src.tracker.score("eog_h") < 0.6
    assert src.tracker.score("eog_v") < 0.6  # the wheel needs both axes, and "eye" fades both
    assert src.tracker.score("blink") > 0.75  # "eye" fades the looks only; blinking stays healthy


def _readings_after_eye_degrade(seed: int, warm: int = 20, after: int = 40) -> list[dict[str, float]]:
    """SyntheticSource.events()' schedule without the clock: a scripted attempt every 0.6 s, and every
    second a rest second plus one reliability reading. Degrade "eye" to 0.3 after `warm` readings."""
    src, script = SyntheticSource(seed=seed), itertools.cycle(DEFAULT_SCRIPT)
    out: list[dict[str, float]] = []
    next_gesture, next_reading = 6, 10  # tenths of a second
    while len(out) < warm + after:
        now = min(next_gesture, next_reading)
        if now == next_gesture:
            src.attempt(next(script))
            next_gesture += 6
        if now == next_reading:
            src.rest_second()
            out.append(src.reliability()["signals"])
            next_reading += 10
            if len(out) == warm:
                src.degrade("eye", 0.3)
    return out[warm:]


def test_eye_degrade_makes_both_eye_signals_fall_together() -> None:
    """One wheel -> scan banner: when the first eye signal has 10 readings below 0.6 (the backend's
    remap_window), the other must already be below 0.6, so the backend's merge window joins them."""
    together = 0
    for seed in range(100):
        r = _readings_after_eye_degrade(seed)
        lost = {
            s: next(i for i in range(9, len(r)) if all(x[s] < 0.6 for x in r[i - 9 : i + 1])) for s in ("eog_h", "eog_v")
        }
        first, other = sorted(lost, key=lost.get)
        together += r[lost[first]][other] < 0.6
        assert max(lost.values()) <= 30  # both are lost within half a minute of the degrade
        assert all(x["blink"] >= 0.6 for x in r)  # blinking stays healthy: double blink takes over SELECT
    assert together >= 95


def test_restore_recovers_reliability() -> None:
    src = SyntheticSource(seed=8)
    src.degrade("blink", 0.2)
    for _ in range(8):
        src.attempt("blink_double")
    src.degrade("blink", 1.0)
    for _ in range(8):
        src.attempt("blink_double")
    assert src.tracker.score("blink") > 0.75


def test_event_stream_sends_gestures_and_reliability() -> None:
    async def collect() -> list[dict]:
        src = SyntheticSource(interval_s=0.05, seed=9)
        src.trigger("blink_double")  # keyboard-style trigger
        out = []
        async for ev in src.events():
            out.append(ev)
            if sum(e["type"] == "reliability" for e in out) >= 2:
                return out
        return out

    events = asyncio.run(asyncio.wait_for(collect(), 5))
    gestures = [e["gesture"] for e in events if e["type"] == "gesture"]
    assert "blink_double" in gestures or len(gestures) > 3
    rel = [e for e in events if e["type"] == "reliability"][-1]
    assert set(rel["signals"]) == {"eog_h", "eog_v", "blink"}


def test_quiet_stream_sends_only_keyboard_gestures_but_still_degrades() -> None:
    """Keyboard demo: scripted attempts and rest false triggers move reliability but never reach the wheel."""

    async def collect() -> tuple[list[dict], SyntheticSource]:
        src = SyntheticSource(interval_s=0.02, seed=9, quiet=True)
        src.degrade("eog_h", 0.0)
        src.trigger("blink_double")
        out = []
        async for ev in src.events():
            out.append(ev)
            if sum(e["type"] == "reliability" for e in out) >= 3:
                return out, src
        return out, src

    events, src = asyncio.run(asyncio.wait_for(collect(), 5))
    gestures = [e["gesture"] for e in events if e["type"] == "gesture"]
    assert gestures == ["blink_double"]
    assert src.tracker.score("eog_h") < 0.6
    assert set(events[-1]["signals"]) == {"eog_h", "eog_v", "blink"}
