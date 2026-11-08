"""Property tests for the input manager: seeded random reliability sequences never break its invariants.

Stdlib `random.Random(seed)` only. Every assertion message carries the seed and step so a failure
reproduces with `gen_sequence(seed)`.
"""

import random

import pytest

from app.input_manager import GESTURE_SOURCE, MAPPING_SOURCES, PRIMARY, InputManager
from app.models import ModeChangeEvent, SignalReliabilityEvent

CFG = {
    "reliability_cutoff": 0.6,
    "recover_cutoff": 0.75,
    "remap_window": 10,
    "recover_window": 20,
    "debounce_ms": 300,
    "merge_window": 12,
}
RIG = ("eog_h", "eog_v", "blink")
SEEDS = range(600)
STEPS = 120
HOVER_STEPS = 60


def clamp(x: float) -> float:
    return min(1.0, max(0.0, x))


def gen_sequence(seed: int, signals: tuple[str, ...] = RIG, steps: int = STEPS) -> list[dict[str, float]]:
    """Per-signal random walks with step drops (like /demo/degrade) and recoveries."""
    rng = random.Random(seed)
    level = {s: rng.uniform(0.5, 1.0) for s in signals}
    seq: list[dict[str, float]] = []
    for _ in range(steps):
        for s in signals:
            roll = rng.random()
            if roll < 0.03:
                level[s] = rng.choice([0.3, 0.1, 0.45])  # degrade
            elif roll < 0.06:
                level[s] = rng.uniform(0.8, 1.0)  # recovery
            else:
                level[s] = clamp(level[s] + rng.gauss(0, 0.04))
        # sometimes only a subset of signals reports in an event
        keys = [s for s in signals if rng.random() < 0.85] or [signals[0]]
        seq.append({s: level[s] for s in keys})
    return seq


def snapshot(im: InputManager) -> tuple[str, dict[str, str | None]]:
    m = im.current_mapping()
    return im.mode, {k: m.get(k) for k in PRIMARY}


def step(im: InputManager, signals: dict[str, float]) -> list[ModeChangeEvent]:
    outs = im.on_reliability(SignalReliabilityEvent(signals=signals, ts=0))
    return [o for o in outs if isinstance(o, ModeChangeEvent)]


def check_invariants(im: InputManager, before, changes: list[ModeChangeEvent], tag: str) -> None:
    mapping = im.current_mapping()
    if im.mode == "wheel":
        assert {"LEFT", "RIGHT", "UP", "DOWN", "SELECT"} <= set(mapping), f"{tag}: wheel without looks/SELECT {mapping}"
        assert "BACK" not in mapping, f"{tag}: wheel has no BACK gesture {mapping}"
    else:
        assert "SELECT" in mapping, f"{tag}: scan without SELECT {mapping}"
    after = snapshot(im)
    assert len(changes) == (1 if after != before else 0), f"{tag}: {len(changes)} mode_change(s), {before} -> {after}"
    if changes:
        assert (changes[0].from_, changes[0].to) == (before[0], after[0]), f"{tag}: bad from/to {changes[0]}"
    assert "HELP" not in mapping and "ACCEPT" not in mapping, f"{tag}: no gesture maps to HELP/ACCEPT {mapping}"
    assert set(mapping.values()) <= set(GESTURE_SOURCE), f"{tag}: unknown gesture in {mapping}"


def check_health_rule(prev: dict[str, bool], im: InputManager, hist: dict[str, list[float]], signals, tag: str) -> None:
    """Health changes only on a full window: 10 readings < cutoff to lose, 20 readings >= recover_cutoff to regain."""
    for source in set(prev) | set(im.healthy):
        if source not in signals:
            assert im.healthy.get(source) == prev.get(source), f"{tag}: {source} health changed without a reading"
            continue
        readings = hist[source]
        if len(readings) == 1:  # the first reading seeds health
            assert im.healthy[source] == (readings[0] >= CFG["reliability_cutoff"]), f"{tag}: bad seed for {source}"
            continue
        expected = prev[source]
        if expected and len(readings) >= CFG["remap_window"]:
            if all(r < CFG["reliability_cutoff"] for r in readings[-CFG["remap_window"]:]):
                expected = False
        elif not expected and len(readings) >= CFG["recover_window"]:
            if all(r >= CFG["recover_cutoff"] for r in readings[-CFG["recover_window"]:]):
                expected = True
        assert im.healthy[source] == expected, (
            f"{tag}: {source} health {prev[source]} -> {im.healthy[source]}, expected {expected}; "
            f"last readings {readings[-CFG['recover_window']:]}"
        )


def target(im: InputManager) -> tuple[str, dict[str, str | None]]:
    """Mode and primary controls the current health calls for, i.e. what a held remap will apply."""
    mode, mapping = im._choose()
    return mode, {k: mapping.get(k) for k in PRIMARY}


def trailing(readings: list[float], pred) -> int:
    n = 0
    for r in reversed(readings):
        if not pred(r):
            break
        n += 1
    return n


def run_under_way(im: InputManager, source: str, readings: list[float], left: int) -> bool:
    """`source` is part-way through a health-changing run that can finish within `left` more readings."""
    if im.healthy.get(source, False):
        k = trailing(readings, lambda r: r < CFG["reliability_cutoff"])
        return k > 0 and CFG["remap_window"] - k <= left
    k = trailing(readings, lambda r: r >= CFG["recover_cutoff"])
    return k > 0 and CFG["recover_window"] - k <= left


def check_merge_window(im: InputManager, hold_start: int | None, i: int, changes, hist, tag: str) -> int | None:
    """A remap may lag health only while held; a hold needs a run under way and ends within merge_window.

    Returns the step the current hold started at (None if no remap is held).
    """
    lagging = snapshot(im) != target(im)
    if changes:
        assert not lagging, f"{tag}: announced {snapshot(im)} but health calls for {target(im)}"
    if lagging:
        assert im.remap_held, f"{tag}: mapping {snapshot(im)} lags health {target(im)} without a held remap"
    if not im.remap_held:
        return None
    hold_start = i if hold_start is None else hold_start
    assert i - hold_start < CFG["merge_window"], f"{tag}: remap held since step {hold_start}"
    left = hold_start + CFG["merge_window"] - i
    assert any(run_under_way(im, s, hist.get(s, []), left) for s in MAPPING_SOURCES), (
        f"{tag}: remap held with no run under way; last readings "
        f"{ {s: hist.get(s, [])[-5:] for s in MAPPING_SOURCES} } health {im.healthy}"
    )
    return hold_start


def run_sequence(seed: int) -> bool:
    """Check every invariant along one random sequence; returns True if a remap was ever held."""
    im = InputManager(cfg=dict(CFG))
    hist: dict[str, list[float]] = {}
    hold_start: int | None = None
    held = False
    for i, signals in enumerate(gen_sequence(seed)):
        before = snapshot(im)
        prev = dict(im.healthy)
        for src, r in signals.items():
            hist.setdefault(src, []).append(r)
        changes = step(im, signals)
        tag = f"seed={seed} step={i}"
        check_invariants(im, before, changes, tag)
        check_health_rule(prev, im, hist, signals, tag)
        hold_start = check_merge_window(im, hold_start, i, changes, hist, tag)
        held = held or hold_start is not None
    return held


@pytest.mark.parametrize("seed", SEEDS)
def test_random_sequences_keep_invariants(seed: int) -> None:
    run_sequence(seed)


def test_random_sequences_exercise_the_merge_window() -> None:
    held = sum(run_sequence(seed) for seed in SEEDS)  # 298 of 600 at the time of writing
    assert held >= 200, f"only {held} of {len(SEEDS)} seeds held a remap"


def run_hover(seed: int, signals: tuple[str, ...]) -> bool:
    """Random warm-up, then every reading in [0.6, 0.75): health cannot change, so neither can the mapping.

    A hover breaks every run, so a remap held at the end of the warm-up lands on the first hover reading.
    Returns True if the warm-up ended in scan mode, i.e. the hover phase exercised the sticky SELECT.
    """
    rng = random.Random(seed)
    im = InputManager(cfg=dict(CFG))
    for warm in gen_sequence(seed, signals, steps=60):
        step(im, warm)
    if im.remap_held:
        step(im, {s: rng.uniform(0.6, 0.7499) for s in signals})
    assert not im.remap_held, f"hover seed={seed}: remap still held after a hover reading"
    frozen = (dict(im.healthy), im.current_mapping(), im.mode)
    in_scan = im.mode == "scan"
    for i in range(HOVER_STEPS):
        changes = step(im, {s: rng.uniform(0.6, 0.7499) for s in signals})
        assert not changes, f"hover seed={seed} step={i}: unexpected mode_change {changes}"
        assert (dict(im.healthy), im.current_mapping(), im.mode) == frozen, (
            f"hover seed={seed} step={i}: {frozen[:2]} -> {(im.healthy, im.current_mapping())}"
        )
    return in_scan


def test_hover_between_cutoffs_never_flips_mapping() -> None:
    checked = sum(run_hover(seed, RIG) for seed in SEEDS)
    # Wheel mode needs both eye channels, so more warm-ups end in the skipped ambiguous-scan state.
    assert checked >= 250, f"only {checked} of {len(SEEDS)} seeds exercised the hover phase"


# --- scan-mode SELECT stays put while hovering (once known gaps, now fixed) ---

def scan_all_unhealthy() -> InputManager:
    im = InputManager(cfg=dict(CFG))
    for _ in range(10):
        step(im, {"eog_h": 0.3, "blink": 0.3})
    return im


def scan_blink_and_brow_healthy() -> InputManager:
    im = InputManager(cfg=dict(CFG))
    for _ in range(10):
        step(im, {"eog_h": 0.3, "blink": 0.7, "brow": 0.65})
    return im


def test_probe_setups_reach_intended_state() -> None:
    im = scan_all_unhealthy()
    assert im.mode == "scan" and not any(im.healthy[s] for s in ("eog_h", "blink"))
    im = scan_blink_and_brow_healthy()
    assert im.mode == "scan" and im.healthy["blink"] and im.healthy["brow"]
    assert not im.healthy["eog_h"]


def test_hover_all_unhealthy_scan_keeps_select() -> None:
    im = scan_all_unhealthy()
    before = im.current_mapping()["SELECT"]
    step(im, {"eog_h": 0.74, "blink": 0.6})
    assert im.current_mapping()["SELECT"] == before


def test_hover_two_healthy_scan_candidates_keeps_select() -> None:
    im = scan_blink_and_brow_healthy()
    before = im.current_mapping()["SELECT"]
    step(im, {"blink": 0.62, "brow": 0.74})
    assert im.current_mapping()["SELECT"] == before
