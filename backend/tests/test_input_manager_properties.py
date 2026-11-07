"""Property tests for the input manager: seeded random reliability sequences never break its invariants.

Stdlib `random.Random(seed)` only. Every assertion message carries the seed and step so a failure
reproduces with `gen_sequence(seed)`.
"""

import random

import pytest

from app.input_manager import GESTURE_SOURCE, PRIMARY, SCAN_SELECT, InputManager
from app.models import ModeChangeEvent, SignalReliabilityEvent

CFG = {
    "reliability_cutoff": 0.6,
    "recover_cutoff": 0.75,
    "remap_window": 10,
    "recover_window": 20,
    "debounce_ms": 300,
}
RIG = ("eog_h", "eog_v", "blink", "jaw")
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
    if im.mode == "split":
        assert "LEFT" in mapping and "RIGHT" in mapping, f"{tag}: split without LEFT/RIGHT {mapping}"
    else:
        assert "SELECT" in mapping, f"{tag}: scan without SELECT {mapping}"
    after = snapshot(im)
    assert len(changes) == (1 if after != before else 0), f"{tag}: {len(changes)} mode_change(s), {before} -> {after}"
    if changes:
        assert (changes[0].from_, changes[0].to) == (before[0], after[0]), f"{tag}: bad from/to {changes[0]}"
    jaw_ok = im.healthy.get("jaw", False)
    assert (mapping.get("HELP") == "jaw_hold") == jaw_ok, f"{tag}: HELP={mapping.get('HELP')} jaw healthy={jaw_ok}"
    assert set(mapping.values()) <= set(GESTURE_SOURCE), f"{tag}: unknown gesture in {mapping}"


@pytest.mark.parametrize("seed", SEEDS)
def test_random_sequences_keep_invariants(seed: int) -> None:
    im = InputManager(cfg=dict(CFG))
    for i, signals in enumerate(gen_sequence(seed)):
        before = snapshot(im)
        changes = step(im, signals)
        check_invariants(im, before, changes, f"seed={seed} step={i}")


def scan_select_is_ambiguous(im: InputManager) -> bool:
    """Scan mode picks SELECT by live reliability unless exactly one candidate is healthy (see probes below)."""
    if im.mode != "scan":
        return False
    return sum(im._ok(g) for g in SCAN_SELECT) != 1


def run_hover(seed: int, signals: tuple[str, ...]) -> bool:
    """Random warm-up, then every reading in [0.6, 0.75): health cannot change, so neither can the mapping.

    Returns False (and checks nothing) when the warm-up ends in the known-ambiguous scan state.
    """
    rng = random.Random(seed)
    im = InputManager(cfg=dict(CFG))
    for warm in gen_sequence(seed, signals, steps=60):
        step(im, warm)
    if scan_select_is_ambiguous(im):
        return False
    frozen = (dict(im.healthy), im.current_mapping(), im.mode)
    for i in range(HOVER_STEPS):
        changes = step(im, {s: rng.uniform(0.6, 0.7499) for s in signals})
        assert not changes, f"hover seed={seed} step={i}: unexpected mode_change {changes}"
        assert (dict(im.healthy), im.current_mapping(), im.mode) == frozen, (
            f"hover seed={seed} step={i}: {frozen[:2]} -> {(im.healthy, im.current_mapping())}"
        )
    return True


def test_hover_between_cutoffs_never_flips_mapping() -> None:
    checked = sum(run_hover(seed, RIG) for seed in SEEDS)
    assert checked >= 400, f"only {checked} of {len(SEEDS)} seeds exercised the hover phase"


# --- known gaps (real findings, app code deliberately untouched) ---

@pytest.mark.xfail(strict=True, reason="scan mode with NO healthy candidate falls back to max live reliability, so hovering flips SELECT")
def test_hover_all_unhealthy_scan_keeps_select() -> None:
    im = InputManager(cfg=dict(CFG))
    for _ in range(10):
        step(im, {"eog_h": 0.3, "blink": 0.3, "jaw": 0.3})
    assert im.mode == "scan"
    before = im.current_mapping()["SELECT"]
    step(im, {"eog_h": 0.74, "blink": 0.6, "jaw": 0.6})
    step(im, {"eog_h": 0.6, "blink": 0.74, "jaw": 0.6})
    assert im.current_mapping()["SELECT"] == before


@pytest.mark.xfail(strict=True, reason="scan mode with 2+ healthy candidates (e.g. blink and brow) re-picks SELECT by live reliability")
def test_hover_two_healthy_scan_candidates_keeps_select() -> None:
    im = InputManager(cfg=dict(CFG))
    step(im, {"eog_h": 0.3, "jaw": 0.3, "blink": 0.7, "brow": 0.65})  # blink and brow healthy via first reading
    for _ in range(9):
        step(im, {"eog_h": 0.3, "jaw": 0.3, "blink": 0.7, "brow": 0.65})
    assert im.mode == "scan" and im.healthy["blink"] and im.healthy["brow"]
    before = im.current_mapping()["SELECT"]
    step(im, {"blink": 0.62, "brow": 0.74})
    assert im.current_mapping()["SELECT"] == before
