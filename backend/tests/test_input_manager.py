"""Input manager tests: mode selection, remap on decline, hysteresis, debounce, HELP.

A reliability "reading" (one value for one signal in a reliability event) counts as one attempt.
"""

from app.input_manager import InputManager
from app.models import GestureEvent, ModeChangeEvent, ReliabilityEvent, SignalReliabilityEvent

CFG = {
    "reliability_cutoff": 0.6,
    "recover_cutoff": 0.75,
    "remap_window": 10,
    "recover_window": 20,
    "debounce_ms": 300,
    "merge_window": 12,
}
LOOK = {"LEFT": "look_left", "RIGHT": "look_right"}
BLINK_JAW = {"LEFT": "blink_double", "RIGHT": "jaw_clench"}


def make(**signals: float) -> InputManager:
    im = InputManager(cfg=dict(CFG))
    if signals:
        feed(im, 1, **signals)
    return im


def feed(im: InputManager, n: int, **signals: float) -> list[ModeChangeEvent]:
    """Send n identical reliability events; return any mode changes."""
    changes: list[ModeChangeEvent] = []
    for _ in range(n):
        for out in im.on_reliability(SignalReliabilityEvent(signals=signals, ts=0)):
            if isinstance(out, ModeChangeEvent):
                changes.append(out)
    return changes


def gesture(im: InputManager, g: str, ts: int = 0) -> list[str]:
    source = {"look_left": "eog_h", "look_right": "eog_h", "blink_double": "blink"}.get(g, "jaw")
    return [c.command.value for c in im.on_gesture(GestureEvent(source=source, gesture=g, confidence=0.9, ts=ts))]


def primary(im: InputManager) -> dict[str, str]:
    m = im.current_mapping()
    return {k: m[k] for k in ("LEFT", "RIGHT") if k in m}


# --- mode selection ---

def test_default_is_split_with_eye_movement() -> None:
    im = make()
    assert im.mode == "split"
    assert primary(im) == LOOK


def test_split_with_eyes_when_all_signals_reliable() -> None:
    im = make(eog_h=0.9, blink=0.9, jaw=0.9)
    assert im.mode == "split"
    assert primary(im) == LOOK
    assert im.current_mapping()["SELECT"] == "jaw_clench"
    assert im.current_mapping()["HELP"] == "jaw_hold"


def test_split_falls_back_to_blink_and_jaw() -> None:
    im = make(eog_h=0.3, blink=0.9, jaw=0.9)
    assert im.mode == "split"
    assert primary(im) == BLINK_JAW


def test_scan_mode_when_one_reliable_gesture() -> None:
    im = make(eog_h=0.3, blink=0.3, jaw=0.9)
    assert im.mode == "scan"
    assert im.current_mapping()["SELECT"] == "jaw_clench"
    assert "LEFT" not in im.current_mapping()


def test_scan_picks_most_reliable_gesture() -> None:
    im = make(eog_h=0.3, blink=0.7, jaw=0.4)
    assert im.mode == "scan"
    assert im.current_mapping()["SELECT"] == "blink_double"


def test_snapshot_matches_contract() -> None:
    im = make(eog_h=0.9, blink=0.9, jaw=0.9)
    snap = im.snapshot()
    assert isinstance(snap, ReliabilityEvent)
    assert snap.mode == "split" and snap.signals["eog_h"] == 0.9


# --- remap on decline ---

def test_remap_after_ten_attempts_below_cutoff_emits_mode_change() -> None:
    im = make(eog_h=0.9, blink=0.9, jaw=0.9)
    assert feed(im, 9, eog_h=0.3, blink=0.9, jaw=0.9) == []
    assert primary(im) == LOOK

    changes = feed(im, 1, eog_h=0.3, blink=0.9, jaw=0.9)
    assert primary(im) == BLINK_JAW
    assert len(changes) == 1
    assert changes[0].from_ == "split" and changes[0].to == "split"
    assert "Eye movement" in changes[0].reason


def test_single_good_reading_resets_decline_count() -> None:
    im = make(eog_h=0.9, blink=0.9, jaw=0.9)
    feed(im, 9, eog_h=0.3, blink=0.9, jaw=0.9)
    feed(im, 1, eog_h=0.65, blink=0.9, jaw=0.9)
    assert feed(im, 9, eog_h=0.3, blink=0.9, jaw=0.9) == []
    assert primary(im) == LOOK


def test_losing_both_eye_channels_switches_to_scan_with_jaw() -> None:
    im = make(eog_h=0.9, blink=0.9, jaw=0.9)
    changes = feed(im, 10, eog_h=0.3, blink=0.3, jaw=0.9)
    assert im.mode == "scan"
    assert im.current_mapping()["SELECT"] == "jaw_clench"
    assert changes[-1].from_ == "split" and changes[-1].to == "scan"
    assert "jaw clench" in changes[-1].reason


def test_scan_keeps_select_while_nothing_is_healthy() -> None:
    im = make(eog_h=0.9, blink=0.9, jaw=0.9)
    feed(im, 10, eog_h=0.3, blink=0.3, jaw=0.3)
    assert im.mode == "scan"
    select = im.current_mapping()["SELECT"]

    # Hovering between the cutoffs changes no signal's health, so SELECT must not move either.
    changes = feed(im, 1, eog_h=0.74, blink=0.6, jaw=0.6) + feed(im, 1, eog_h=0.6, blink=0.74, jaw=0.6)
    assert changes == []
    assert im.current_mapping()["SELECT"] == select


def test_scan_repicks_select_when_its_signal_becomes_unhealthy() -> None:
    im = make(eog_h=0.3, blink=0.3, jaw=0.9)
    assert im.current_mapping()["SELECT"] == "jaw_clench"
    feed(im, 9, jaw=0.3)
    changes = feed(im, 1, jaw=0.3, brow=0.9)
    assert im.mode == "scan" and im.current_mapping()["SELECT"] == "brow_raise"
    assert len(changes) == 1 and "Jaw clench" in changes[0].reason


def test_unmapped_signal_decline_does_not_announce() -> None:
    im = make(eog_h=0.9, blink=0.9, jaw=0.9)  # look mapping; blink only used for BACK
    assert feed(im, 10, eog_h=0.9, blink=0.3, jaw=0.9) == []
    assert primary(im) == LOOK


# --- merge window: losses a few readings apart give one banner ---

EYE_TO_JAW = "Eye movement and blinking reliability fell below 60%. Switching to scan mode with jaw clench to select."


def staggered(im: InputManager, first: str, second: str, gap: int, n: int, to: float = 0.3) -> list[ModeChangeEvent]:
    """`first` moves to `to` now and `second` follows `gap` readings later; jaw stays healthy."""
    before = 0.9 if to < 0.6 else 0.3
    changes: list[ModeChangeEvent] = []
    for i in range(n):
        signals = {first: to, second: to if i >= gap else before, "jaw": 0.9}
        changes += feed(im, 1, **signals)
    return changes


def test_eye_signals_lost_a_few_readings_apart_give_one_banner() -> None:
    for gap in (1, 2, 3):
        im = make(eog_h=0.9, blink=0.9, jaw=0.9)
        changes = staggered(im, "eog_h", "blink", gap, n=40)
        assert len(changes) == 1, (gap, [c.reason for c in changes])
        assert (changes[0].from_, changes[0].to) == ("split", "scan")
        assert changes[0].reason == EYE_TO_JAW
        assert im.mode == "scan" and im.current_mapping()["SELECT"] == "jaw_clench"


def test_blink_lost_first_still_names_both_eye_signals() -> None:
    for gap in (1, 2, 3):
        im = make(eog_h=0.9, blink=0.9, jaw=0.9)
        changes = staggered(im, "blink", "eog_h", gap, n=40)
        assert [(c.from_, c.to, c.reason) for c in changes] == [("split", "scan", EYE_TO_JAW)], gap


def test_eye_loss_waits_at_most_merge_window_readings() -> None:
    im = make(eog_h=0.9, blink=0.9, jaw=0.9)
    # blink hovers just below the cutoff and keeps resetting its streak, so it never fails
    for i in range(9):
        feed(im, 1, eog_h=0.3, blink=0.5, jaw=0.9)
    lost_at = None
    for i in range(30):
        changes = feed(im, 1, eog_h=0.3, blink=0.5 if i % 5 else 0.7, jaw=0.9)
        if lost_at is None and not im.healthy["eog_h"]:
            lost_at = i
        if changes:
            assert i - lost_at <= CFG["merge_window"]
            assert changes[0].reason.startswith("Eye movement reliability")
            break
    else:
        raise AssertionError("eog_h loss never announced")
    assert primary(im) == BLINK_JAW


def test_lone_eye_loss_with_blink_healthy_is_not_delayed() -> None:
    im = make(eog_h=0.9, blink=0.9, jaw=0.9)
    assert feed(im, 9, eog_h=0.3, blink=0.9, jaw=0.9) == []
    changes = feed(im, 1, eog_h=0.3, blink=0.9, jaw=0.9)
    assert [(c.from_, c.to) for c in changes] == [("split", "split")]
    assert changes[0].reason == "Eye movement reliability fell below 60%. Switching to double blink and jaw clench."


def test_mapping_is_held_while_a_second_loss_may_join() -> None:
    im = make(eog_h=0.9, blink=0.9, jaw=0.9)
    staggered(im, "eog_h", "blink", gap=3, n=10)  # eog_h lost; blink 3 readings from failing
    assert not im.healthy["eog_h"]
    assert primary(im) == LOOK and im.mode == "split"
    assert im.current_mapping()["HELP"] == "jaw_hold"


def test_eye_regain_gives_one_banner_back_to_eye_movement() -> None:
    im = make(eog_h=0.9, blink=0.9, jaw=0.9)
    feed(im, 10, eog_h=0.3, blink=0.3, jaw=0.9)
    assert im.mode == "scan"
    changes = staggered(im, "eog_h", "blink", gap=3, n=40, to=0.9)
    assert [(c.from_, c.to) for c in changes] == [("scan", "split")], [c.reason for c in changes]
    assert changes[0].reason == "Eye movement and blinking are reliable again. Switching back to eye movement."
    assert primary(im) == LOOK and im.current_mapping()["BACK"] == "blink_double"


def test_regain_and_loss_cycles_do_not_flap() -> None:
    im = make(eog_h=0.9, blink=0.9, jaw=0.9)
    seen: list[tuple[str, str]] = []
    for cycle in range(3):
        seen += [(c.from_, c.to) for c in staggered(im, "eog_h", "blink", gap=2, n=40)]
        seen += [(c.from_, c.to) for c in staggered(im, "eog_h", "blink", gap=2, n=60, to=0.9)]
    assert seen == [("split", "scan"), ("scan", "split")] * 3


def test_force_mode_during_a_held_remap_applies_it() -> None:
    im = make(eog_h=0.9, blink=0.9, jaw=0.9)
    staggered(im, "eog_h", "blink", gap=3, n=10)
    change = im.force_mode("scan")
    assert change is not None and change.to == "scan"
    assert im.current_mapping()["SELECT"] == "jaw_clench"
    # the held eye remap was absorbed into the manual switch: blink's later loss is not announced again
    assert staggered(im, "eog_h", "blink", gap=0, n=10) == []


def test_force_mode_to_the_current_mode_applies_a_held_remap() -> None:
    im = make(eog_h=0.9, blink=0.9, jaw=0.9)
    staggered(im, "eog_h", "blink", gap=3, n=10)
    assert im.remap_held and im.mode == "split"
    change = im.force_mode("split")
    assert change is not None and (change.from_, change.to) == ("split", "split")
    assert change.reason == "Eye movement reliability fell below 60%. Switching to double blink and jaw clench."
    assert primary(im) == BLINK_JAW and not im.remap_held
    assert im.force_mode("split") is None


def test_force_mode_to_the_current_mode_lands_a_held_split_to_scan_remap() -> None:
    im = make(eog_h=0.9, blink=0.9, jaw=0.9)
    for i in range(12):  # blink fails first (BACK only), then eog_h while jaw is part-way into a low run
        feed(im, 1, eog_h=0.3 if i >= 2 else 0.9, blink=0.3, jaw=0.3 if i >= 8 else 0.9)
    assert im.remap_held and im.mode == "split" and primary(im) == LOOK
    change = im.force_mode("split")
    assert change is not None and (change.from_, change.to) == ("split", "scan")
    assert change.reason == EYE_TO_JAW
    assert im.override is None and not im.remap_held
    assert im.current_mapping() == {"SELECT": "jaw_clench", "HELP": "jaw_hold"}
    for _ in range(25):  # jaw recovers: the board stays on jaw scan, never the dead eye fallback
        feed(im, 1, eog_h=0.3, blink=0.3, jaw=0.9)
        assert im.mode == "scan" and im.current_mapping()["SELECT"] == "jaw_clench"


# --- merge window: only a streak under way holds a remap, never a steady hover ---

def test_shaky_jaw_does_not_delay_an_eye_loss() -> None:
    im = make(eog_h=0.9, blink=0.9, jaw=0.9)
    assert feed(im, 9, eog_h=0.3, blink=0.9, jaw=0.7) == []
    changes = feed(im, 1, eog_h=0.3, blink=0.9, jaw=0.7)
    assert [(c.from_, c.to) for c in changes] == [("split", "split")]
    assert not im.remap_held


def test_jaw_loss_remaps_at_once_while_blink_hovers() -> None:
    im = make(eog_h=0.3, blink=0.9, jaw=0.9)
    assert primary(im) == BLINK_JAW
    assert feed(im, 9, eog_h=0.3, blink=0.7, jaw=0.3) == []
    changes = feed(im, 1, eog_h=0.3, blink=0.7, jaw=0.3)
    assert [(c.from_, c.to) for c in changes] == [("split", "scan")]
    assert im.current_mapping() == {"SELECT": "blink_double"}  # dead jaw no longer RIGHT, HELP gone


def test_unhealthy_hover_does_not_delay_a_regain() -> None:
    im = make(eog_h=0.3, blink=0.3, jaw=0.9)
    assert im.mode == "scan"
    assert feed(im, 19, eog_h=0.65, blink=0.9, jaw=0.9) == []
    changes = feed(im, 1, eog_h=0.65, blink=0.9, jaw=0.9)
    assert [(c.from_, c.to) for c in changes] == [("scan", "split")]
    assert primary(im) == BLINK_JAW


def test_hold_ends_when_the_trailing_run_breaks() -> None:
    im = make(eog_h=0.9, blink=0.9, jaw=0.9)
    staggered(im, "eog_h", "blink", gap=3, n=10)  # eog_h lost; blink 7 readings into its run
    assert im.remap_held
    changes = feed(im, 1, eog_h=0.3, blink=0.9, jaw=0.9)  # blink recovers: nothing left to wait for
    assert [(c.from_, c.to) for c in changes] == [("split", "split")]
    assert primary(im) == BLINK_JAW and not im.remap_held


def test_loss_and_regain_in_one_banner_name_both() -> None:
    im = make(eog_h=0.3, blink=0.9, jaw=0.9)
    assert primary(im) == BLINK_JAW
    feed(im, 10, eog_h=0.9, blink=0.9, jaw=0.9)
    changes = feed(im, 10, eog_h=0.9, blink=0.9, jaw=0.3)  # eog_h regains on jaw's 10th low reading
    assert len(changes) == 1
    assert changes[0].reason == (
        "Jaw clench reliability fell below 60% and eye movement is reliable again. Switching to eye movement."
    )
    assert primary(im) == LOOK


# --- hysteresis ---

def test_hysteresis_requires_twenty_attempts_above_recover_cutoff() -> None:
    im = make(eog_h=0.9, blink=0.9, jaw=0.9)
    feed(im, 10, eog_h=0.3, blink=0.9, jaw=0.9)
    assert primary(im) == BLINK_JAW

    # Between the cutoffs: above 0.6 but below 0.75 never switches back.
    assert feed(im, 30, eog_h=0.7, blink=0.9, jaw=0.9) == []
    assert feed(im, 19, eog_h=0.8, blink=0.9, jaw=0.9) == []
    assert primary(im) == BLINK_JAW

    changes = feed(im, 1, eog_h=0.8, blink=0.9, jaw=0.9)
    assert primary(im) == LOOK
    assert "reliable again" in changes[0].reason


def test_no_flapping_around_cutoff() -> None:
    im = make(eog_h=0.9, blink=0.9, jaw=0.9)
    changes: list[ModeChangeEvent] = []
    for i in range(100):
        changes += feed(im, 1, eog_h=0.55 if i % 2 else 0.65, blink=0.9, jaw=0.9)
    assert changes == []


# --- gestures -> commands ---

def test_gestures_follow_current_mapping() -> None:
    im = make(eog_h=0.9, blink=0.9, jaw=0.9)
    assert gesture(im, "look_left") == ["LEFT"]
    assert gesture(im, "look_right", ts=1000) == ["RIGHT"]
    assert gesture(im, "jaw_clench", ts=2000) == ["SELECT"]


def test_gestures_from_remapped_signal_are_ignored() -> None:
    im = make(eog_h=0.9, blink=0.9, jaw=0.9)
    feed(im, 10, eog_h=0.3, blink=0.9, jaw=0.9)
    assert gesture(im, "look_left") == []
    assert gesture(im, "blink_double", ts=1000) == ["LEFT"]


def test_scan_mode_jaw_clench_is_select() -> None:
    im = make(eog_h=0.3, blink=0.3, jaw=0.9)
    assert gesture(im, "jaw_clench") == ["SELECT"]
    assert gesture(im, "look_left", ts=1000) == []


# --- debounce ---

def test_debounce_drops_duplicate_within_300ms() -> None:
    im = make(eog_h=0.9, blink=0.9, jaw=0.9)
    assert gesture(im, "look_left", ts=0) == ["LEFT"]
    assert gesture(im, "look_left", ts=200) == []
    assert gesture(im, "look_left", ts=500) == ["LEFT"]


def test_debounce_is_per_command() -> None:
    im = make(eog_h=0.9, blink=0.9, jaw=0.9)
    assert gesture(im, "look_left", ts=0) == ["LEFT"]
    assert gesture(im, "look_right", ts=100) == ["RIGHT"]


# --- HELP ---

def test_help_requires_hold_to_confirm() -> None:
    """A short clench never raises HELP; only jaw_hold (detector-confirmed ~2 s hold) does."""
    im = make(eog_h=0.9, blink=0.9, jaw=0.9)
    assert "HELP" not in gesture(im, "jaw_clench")
    assert gesture(im, "jaw_hold", ts=1000) == ["HELP"]


def test_help_available_in_scan_mode() -> None:
    im = make(eog_h=0.3, blink=0.3, jaw=0.9)
    assert gesture(im, "jaw_hold") == ["HELP"]


# --- manual override (keyboard sim M key) ---

def test_force_mode_to_scan_and_back() -> None:
    im = make(eog_h=0.9, blink=0.9, jaw=0.9)
    change = im.force_mode("scan")
    assert change is not None and change.to == "scan"
    assert im.mode == "scan" and im.current_mapping()["SELECT"] == "jaw_clench"

    change = im.force_mode("split")
    assert change is not None and change.to == "split"
    assert primary(im) == LOOK
    assert im.force_mode("split") is None
