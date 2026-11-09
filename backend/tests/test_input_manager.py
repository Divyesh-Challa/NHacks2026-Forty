"""Input manager tests: wheel/scan selection, remap on decline, hysteresis, debounce.

A reliability "reading" (one value for one signal in a reliability event) counts as one attempt.
There are no jaw/HELP gestures: HELP is a wheel slot confirmed with SELECT (double blink).
"""

from app.config import INPUT
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
LOOK = {"LEFT": "look_left", "RIGHT": "look_right", "UP": "look_up", "DOWN": "look_down"}


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
    source = {
        "look_left": "eog_h",
        "look_right": "eog_h",
        "look_up": "eog_v",
        "look_down": "eog_v",
        "blink_double": "blink",
    }.get(g, "brow")
    return [c.command.value for c in im.on_gesture(GestureEvent(source=source, gesture=g, confidence=0.9, ts=ts))]


def primary(im: InputManager) -> dict[str, str]:
    m = im.current_mapping()
    return {k: m[k] for k in ("LEFT", "RIGHT", "UP", "DOWN") if k in m}


def test_config_has_every_input_key() -> None:
    assert set(CFG) <= set(INPUT), set(CFG) - set(INPUT)


# --- mode selection ---

def test_default_is_wheel_with_eye_movement() -> None:
    im = make()
    assert im.mode == "wheel"
    assert primary(im) == LOOK


def test_wheel_mapping_when_all_signals_reliable() -> None:
    im = make(eog_h=0.9, eog_v=0.9, blink=0.9)
    assert im.mode == "wheel"
    assert primary(im) == LOOK
    m = im.current_mapping()
    assert m["SELECT"] == "blink_double"
    assert "ACCEPT" not in m and "HELP" not in m  # no gesture for either
    assert "BACK" not in m  # going back is looking at the kept slot


def test_wheel_needs_vertical_eye_movement_too() -> None:
    im = make(eog_h=0.9, eog_v=0.3, blink=0.9)
    assert im.mode == "scan"


def test_wheel_needs_a_finish_gesture() -> None:
    im = make(eog_h=0.9, eog_v=0.9, blink=0.3)
    assert im.mode == "scan"


def test_scan_when_eyes_unreliable() -> None:
    im = make(eog_h=0.3, blink=0.9)
    assert im.mode == "scan"
    assert im.current_mapping() == {"SELECT": "blink_double"}


def test_snapshot_matches_contract() -> None:
    im = make(eog_h=0.9, blink=0.9)
    snap = im.snapshot()
    assert isinstance(snap, ReliabilityEvent)
    assert snap.mode == "wheel" and snap.signals["eog_h"] == 0.9


# --- remap on decline ---

def test_remap_after_ten_attempts_below_cutoff_emits_mode_change() -> None:
    im = make(eog_h=0.9, blink=0.9)
    assert feed(im, 9, eog_h=0.3, blink=0.9) == []
    assert primary(im) == LOOK

    changes = feed(im, 1, eog_h=0.3, blink=0.9)
    assert im.mode == "scan"
    assert len(changes) == 1
    assert changes[0].from_ == "wheel" and changes[0].to == "scan"
    assert "Eye movement" in changes[0].reason
    assert "double blink" in changes[0].reason


def test_single_good_reading_resets_decline_count() -> None:
    im = make(eog_h=0.9, blink=0.9)
    feed(im, 9, eog_h=0.3, blink=0.9)
    feed(im, 1, eog_h=0.65, blink=0.9)
    assert feed(im, 9, eog_h=0.3, blink=0.9) == []
    assert primary(im) == LOOK


def test_losing_the_finish_gesture_switches_to_scan() -> None:
    im = make(eog_h=0.9, blink=0.9)
    changes = feed(im, 10, eog_h=0.9, blink=0.3)
    assert im.mode == "scan"
    assert changes[-1].from_ == "wheel" and changes[-1].to == "scan"


# --- scan-mode SELECT is sticky ---

def test_scan_keeps_select_while_nothing_is_healthy() -> None:
    im = make(eog_h=0.9, eog_v=0.9, blink=0.9)
    feed(im, 10, eog_h=0.3, eog_v=0.3, blink=0.3)
    assert im.mode == "scan"
    select = im.current_mapping()["SELECT"]

    # Hovering between the cutoffs changes no signal's health, so SELECT must not move either.
    changes = feed(im, 1, eog_h=0.74, eog_v=0.6, blink=0.6) + feed(im, 1, eog_h=0.6, eog_v=0.6, blink=0.74)
    assert changes == []
    assert im.current_mapping()["SELECT"] == select


def test_scan_keeps_select_while_another_candidate_reads_higher() -> None:
    im = make(eog_h=0.3, blink=0.7, brow=0.65)
    assert im.current_mapping() == {"SELECT": "blink_double"}
    assert feed(im, 1, eog_h=0.3, blink=0.62, brow=0.74) == []
    assert im.current_mapping() == {"SELECT": "blink_double"}


def test_scan_repicks_select_when_its_signal_becomes_unhealthy() -> None:
    im = make(eog_h=0.3, blink=0.9)
    assert im.current_mapping()["SELECT"] == "blink_double"
    feed(im, 9, blink=0.3)
    changes = feed(im, 1, blink=0.3, brow=0.9)
    assert im.mode == "scan" and im.current_mapping()["SELECT"] == "brow_raise"
    assert len(changes) == 1 and changes[0].reason.startswith("Blinking reliability fell below 60%")


def test_unmapped_signal_decline_does_not_announce() -> None:
    im = make(eog_h=0.9, eog_v=0.9, blink=0.9, brow=0.9)  # wheel finishes with blink; brow is unused
    assert feed(im, 10, eog_h=0.9, eog_v=0.9, blink=0.9, brow=0.3) == []
    assert primary(im) == LOOK and im.current_mapping()["SELECT"] == "blink_double"


# --- merge window: losses a few readings apart give one banner ---

EYES_TO_BLINK = (
    "Eye movement and vertical eye movement reliability fell below 60%. "
    "Switching to scan mode with double blink to select."
)
EYES_BACK = (
    "Eye movement and vertical eye movement are reliable again. "
    "Switching back to eye movement with double blink to finish."
)


def staggered(im: InputManager, first: str, second: str, gap: int, n: int, to: float = 0.3) -> list[ModeChangeEvent]:
    """`first` moves to `to` now and `second` follows `gap` readings later; blink stays healthy."""
    before = 0.9 if to < 0.6 else 0.3
    changes: list[ModeChangeEvent] = []
    for i in range(n):
        signals = {first: to, second: to if i >= gap else before, "blink": 0.9}
        changes += feed(im, 1, **signals)
    return changes


def test_eye_signals_lost_a_few_readings_apart_give_one_banner() -> None:
    for gap in (1, 2, 3):
        im = make(eog_h=0.9, eog_v=0.9, blink=0.9)
        changes = staggered(im, "eog_h", "eog_v", gap, n=40)
        assert len(changes) == 1, (gap, [c.reason for c in changes])
        assert (changes[0].from_, changes[0].to) == ("wheel", "scan")
        assert changes[0].reason == EYES_TO_BLINK
        assert im.mode == "scan" and im.current_mapping() == {"SELECT": "blink_double"}


def test_vertical_lost_first_still_names_both_eye_signals() -> None:
    for gap in (1, 2, 3):
        im = make(eog_h=0.9, eog_v=0.9, blink=0.9)
        changes = staggered(im, "eog_v", "eog_h", gap, n=40)
        assert [(c.from_, c.to, c.reason) for c in changes] == [("wheel", "scan", EYES_TO_BLINK)], gap


def test_eye_loss_waits_at_most_merge_window_readings() -> None:
    im = make(eog_h=0.9, eog_v=0.9, blink=0.9)
    # eog_v hovers just below the cutoff and keeps resetting its streak, so it never fails
    for i in range(9):
        feed(im, 1, eog_h=0.3, eog_v=0.5, blink=0.9)
    lost_at = None
    for i in range(30):
        changes = feed(im, 1, eog_h=0.3, eog_v=0.5 if i % 5 else 0.7, blink=0.9)
        if lost_at is None and not im.healthy["eog_h"]:
            lost_at = i
        if changes:
            assert i - lost_at <= CFG["merge_window"]
            assert changes[0].reason.startswith("Eye movement reliability")
            break
    else:
        raise AssertionError("eog_h loss never announced")
    assert im.mode == "scan" and im.current_mapping() == {"SELECT": "blink_double"}


def test_lone_eye_loss_with_vertical_healthy_is_not_delayed() -> None:
    im = make(eog_h=0.9, eog_v=0.9, blink=0.9)
    assert feed(im, 9, eog_h=0.3, eog_v=0.9, blink=0.9) == []
    changes = feed(im, 1, eog_h=0.3, eog_v=0.9, blink=0.9)
    assert [(c.from_, c.to) for c in changes] == [("wheel", "scan")]
    assert changes[0].reason == "Eye movement reliability fell below 60%. Switching to scan mode with double blink to select."


def test_mapping_is_held_while_a_second_loss_may_join() -> None:
    im = make(eog_h=0.9, eog_v=0.9, blink=0.9)
    staggered(im, "eog_h", "eog_v", gap=3, n=10)  # eog_h lost; eog_v 3 readings from failing
    assert not im.healthy["eog_h"]
    assert im.remap_held
    assert primary(im) == LOOK and im.mode == "wheel"
    assert im.current_mapping()["SELECT"] == "blink_double"


def test_eye_regain_gives_one_banner_back_to_eye_movement() -> None:
    im = make(eog_h=0.9, eog_v=0.9, blink=0.9)
    feed(im, 10, eog_h=0.3, eog_v=0.3, blink=0.9)
    assert im.mode == "scan"
    changes = staggered(im, "eog_h", "eog_v", gap=3, n=40, to=0.9)
    assert [(c.from_, c.to) for c in changes] == [("scan", "wheel")], [c.reason for c in changes]
    assert changes[0].reason == EYES_BACK
    assert primary(im) == LOOK and im.current_mapping()["SELECT"] == "blink_double"


def test_regain_and_loss_cycles_do_not_flap() -> None:
    im = make(eog_h=0.9, eog_v=0.9, blink=0.9)
    seen: list[tuple[str, str]] = []
    for cycle in range(3):
        seen += [(c.from_, c.to) for c in staggered(im, "eog_h", "eog_v", gap=2, n=40)]
        seen += [(c.from_, c.to) for c in staggered(im, "eog_h", "eog_v", gap=2, n=60, to=0.9)]
    assert seen == [("wheel", "scan"), ("scan", "wheel")] * 3


def test_force_mode_during_a_held_remap_applies_it() -> None:
    im = make(eog_h=0.9, eog_v=0.9, blink=0.9)
    staggered(im, "eog_h", "eog_v", gap=3, n=10)
    change = im.force_mode("scan")
    assert change is not None and change.to == "scan"
    assert im.current_mapping()["SELECT"] == "blink_double"
    # the held eye remap was absorbed into the manual switch: eog_v's later loss is not announced again
    assert staggered(im, "eog_h", "eog_v", gap=0, n=10) == []


def test_force_mode_to_the_current_mode_applies_a_held_remap() -> None:
    im = make(eog_h=0.9, eog_v=0.9, blink=0.9)
    staggered(im, "eog_h", "eog_v", gap=3, n=10)
    assert im.remap_held and im.mode == "wheel"
    change = im.force_mode("wheel")
    assert change is not None and (change.from_, change.to) == ("wheel", "scan")
    assert change.reason == "Eye movement reliability fell below 60%. Switching to scan mode with double blink to select."
    assert im.override is None and not im.remap_held
    assert im.force_mode("scan") is None


def test_force_mode_to_the_current_mode_lands_a_held_wheel_to_scan_remap() -> None:
    im = make(eog_h=0.9, eog_v=0.9, blink=0.9, brow=0.9)
    for i in range(12):  # brow fails first (unused), then eog_h while eog_v is part-way into a low run
        feed(im, 1, eog_h=0.3 if i >= 2 else 0.9, eog_v=0.3 if i >= 8 else 0.9, blink=0.9, brow=0.3)
    assert im.remap_held and im.mode == "wheel" and primary(im) == LOOK
    change = im.force_mode("wheel")
    assert change is not None and (change.from_, change.to) == ("wheel", "scan")
    assert change.reason == (
        "Eye movement and eyebrow raise reliability fell below 60%. Switching to scan mode with double blink to select."
    )
    assert im.override is None and not im.remap_held
    assert im.current_mapping() == {"SELECT": "blink_double"}
    for _ in range(25):  # the board stays on blink scan, never the dead eye-wheel fallback
        feed(im, 1, eog_h=0.3, eog_v=0.3, blink=0.9, brow=0.3)
        assert im.mode == "scan" and im.current_mapping() == {"SELECT": "blink_double"}


# --- merge window: only a streak under way holds a remap, never a steady hover ---

def test_shaky_vertical_does_not_delay_an_eye_loss() -> None:
    im = make(eog_h=0.9, eog_v=0.9, blink=0.9)
    assert feed(im, 9, eog_h=0.3, eog_v=0.7, blink=0.9) == []
    changes = feed(im, 1, eog_h=0.3, eog_v=0.7, blink=0.9)
    assert [(c.from_, c.to) for c in changes] == [("wheel", "scan")]
    assert not im.remap_held


def test_blink_loss_remaps_at_once_while_vertical_hovers() -> None:
    im = make(eog_h=0.9, eog_v=0.9, blink=0.9)
    assert feed(im, 9, eog_h=0.9, eog_v=0.7, blink=0.3) == []
    changes = feed(im, 1, eog_h=0.9, eog_v=0.7, blink=0.3)
    assert [(c.from_, c.to) for c in changes] == [("wheel", "scan")]
    assert not im.remap_held
    assert im.current_mapping() == {"SELECT": "look_right"}  # no finish gesture left, so no wheel


def test_unhealthy_hover_does_not_delay_a_regain() -> None:
    im = make(eog_h=0.9, eog_v=0.9, blink=0.3, brow=0.3)
    assert im.mode == "scan"
    assert feed(im, 19, eog_h=0.9, eog_v=0.9, blink=0.9, brow=0.65) == []
    changes = feed(im, 1, eog_h=0.9, eog_v=0.9, blink=0.9, brow=0.65)
    assert [(c.from_, c.to) for c in changes] == [("scan", "wheel")]
    assert primary(im) == LOOK and im.current_mapping()["SELECT"] == "blink_double"


def test_hold_ends_when_the_trailing_run_breaks() -> None:
    im = make(eog_h=0.9, eog_v=0.9, blink=0.9)
    staggered(im, "eog_h", "eog_v", gap=3, n=10)  # eog_h lost; eog_v 7 readings into its run
    assert im.remap_held
    changes = feed(im, 1, eog_h=0.3, eog_v=0.9, blink=0.9)  # eog_v recovers: nothing left to wait for
    assert [(c.from_, c.to) for c in changes] == [("wheel", "scan")]
    assert changes[0].reason.startswith("Eye movement reliability fell below 60%.")
    assert not im.remap_held


def test_loss_and_regain_in_one_banner_name_both() -> None:
    im = make(eog_h=0.3, eog_v=0.9, blink=0.9, brow=0.9)
    assert im.mode == "scan" and im.current_mapping() == {"SELECT": "blink_double"}
    feed(im, 10, eog_h=0.9, eog_v=0.9, blink=0.9, brow=0.9)
    changes = feed(im, 10, eog_h=0.9, eog_v=0.9, blink=0.3, brow=0.9)  # eog_h regains on blink's 10th low reading
    assert len(changes) == 1
    assert changes[0].reason == (
        "Blinking reliability fell below 60% and eye movement is reliable again. "
        "Switching to eye movement with eyebrow raise to finish."
    )
    assert primary(im) == LOOK and im.current_mapping()["SELECT"] == "brow_raise"


# --- hysteresis ---

def test_hysteresis_requires_twenty_attempts_above_recover_cutoff() -> None:
    im = make(eog_h=0.9, blink=0.9)
    feed(im, 10, eog_h=0.3, blink=0.9)
    assert im.mode == "scan"

    # Between the cutoffs: above 0.6 but below 0.75 never switches back.
    assert feed(im, 30, eog_h=0.7, blink=0.9) == []
    assert feed(im, 19, eog_h=0.8, blink=0.9) == []
    assert im.mode == "scan"

    changes = feed(im, 1, eog_h=0.8, blink=0.9)
    assert im.mode == "wheel" and primary(im) == LOOK
    assert "reliable again" in changes[0].reason


def test_no_flapping_around_cutoff() -> None:
    im = make(eog_h=0.9, blink=0.9)
    changes: list[ModeChangeEvent] = []
    for i in range(100):
        changes += feed(im, 1, eog_h=0.55 if i % 2 else 0.65, blink=0.9)
    assert changes == []


# --- gestures -> commands ---

def test_gestures_follow_current_mapping() -> None:
    im = make(eog_h=0.9, blink=0.9)
    assert gesture(im, "look_left") == ["LEFT"]
    assert gesture(im, "look_right", ts=1000) == ["RIGHT"]
    assert gesture(im, "look_up", ts=3000) == ["UP"]
    assert gesture(im, "look_down", ts=4000) == ["DOWN"]
    assert gesture(im, "blink_double", ts=5000) == ["SELECT"]


def test_gestures_from_remapped_signal_are_ignored() -> None:
    im = make(eog_h=0.9, blink=0.9)
    feed(im, 10, eog_h=0.3, blink=0.9)
    assert gesture(im, "look_left") == []
    assert gesture(im, "look_up", ts=1000) == []
    assert gesture(im, "blink_double", ts=2000) == ["SELECT"]


def test_scan_mode_double_blink_is_select() -> None:
    im = make(eog_h=0.3, blink=0.9)
    assert gesture(im, "blink_double") == ["SELECT"]
    assert gesture(im, "look_left", ts=1000) == []


# --- debounce ---

def test_debounce_drops_duplicate_within_300ms() -> None:
    im = make(eog_h=0.9, blink=0.9)
    assert gesture(im, "look_left", ts=0) == ["LEFT"]
    assert gesture(im, "look_left", ts=200) == []
    assert gesture(im, "look_left", ts=500) == ["LEFT"]


def test_debounce_is_per_command() -> None:
    im = make(eog_h=0.9, blink=0.9)
    assert gesture(im, "look_left", ts=0) == ["LEFT"]
    assert gesture(im, "look_right", ts=100) == ["RIGHT"]


# --- manual override (keyboard sim M key) ---

def test_force_mode_to_scan_and_back() -> None:
    im = make(eog_h=0.9, blink=0.9)
    change = im.force_mode("scan")
    assert change is not None and change.to == "scan"
    assert im.mode == "scan" and im.current_mapping()["SELECT"] == "blink_double"

    change = im.force_mode("wheel")
    assert change is not None and change.to == "wheel"
    assert primary(im) == LOOK
    assert im.force_mode("wheel") is None
