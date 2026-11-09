"""Input manager tests: wheel/scan selection, remap on decline, hysteresis, debounce.

A reliability "reading" (one value for one signal in a reliability event) counts as one attempt.
There are no jaw/HELP gestures: HELP is a wheel slot confirmed with SELECT (double blink).
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


# --- merge window: staggered wheel/scan changes share a banner ---


def staggered(im: InputManager, first: str, second: str, gap: int, n: int, to: float = 0.3) -> list[ModeChangeEvent]:
    before = 0.9 if to < 0.6 else 0.3
    changes: list[ModeChangeEvent] = []
    for i in range(n):
        changes += feed(im, 1, **{first: to, second: to if i >= gap else before})
    return changes


def test_eye_signals_lost_a_few_readings_apart_give_one_banner() -> None:
    for gap in (1, 2, 3):
        im = make(eog_h=.9, eog_v=.9, blink=.9)
        changes = staggered(im, 'eog_h', 'eog_v', gap, 40)
        assert len(changes) == 1
        assert (changes[0].from_, changes[0].to) == ('wheel', 'scan')
        assert 'Eye movement and vertical eye movement reliability fell below' in changes[0].reason
        assert im.current_mapping() == {'SELECT': 'blink_double'}


def test_mapping_is_held_while_a_second_loss_may_join() -> None:
    im = make(eog_h=.9, eog_v=.9, blink=.9)
    staggered(im, 'eog_h', 'eog_v', 3, 10)
    assert not im.healthy['eog_h'] and im.remap_held
    assert im.mode == 'wheel' and primary(im) == LOOK
    assert 'HELP' not in im.current_mapping() and 'BACK' not in im.current_mapping()


def test_hold_ends_when_the_trailing_run_breaks() -> None:
    im = make(eog_h=.9, eog_v=.9, blink=.9)
    staggered(im, 'eog_h', 'eog_v', 3, 10)
    changes = feed(im, 1, eog_h=.3, eog_v=.9)
    assert len(changes) == 1 and im.mode == 'scan' and not im.remap_held


def test_regain_merges_both_eye_channels() -> None:
    im = make(eog_h=.3, eog_v=.3, blink=.9)
    changes = staggered(im, 'eog_h', 'eog_v', 3, 40, to=.9)
    assert len(changes) == 1 and im.mode == 'wheel'
    assert 'reliable again' in changes[0].reason
    assert primary(im) == LOOK


def test_force_mode_to_current_mode_lands_held_remap() -> None:
    im = make(eog_h=.9, eog_v=.9, blink=.9)
    staggered(im, 'eog_h', 'eog_v', 3, 10)
    change = im.force_mode('wheel')
    assert change is not None and change.to == 'scan'
    assert not im.remap_held and im.override is None


def test_force_mode_to_scan_during_hold() -> None:
    im = make(eog_h=.9, eog_v=.9, blink=.9)
    staggered(im, 'eog_h', 'eog_v', 3, 10)
    assert im.force_mode('scan').to == 'scan'
    assert not im.remap_held and im.current_mapping() == {'SELECT': 'blink_double'}


def test_actual_config_handles_loss_and_recovery() -> None:
    # Exercise production TOML, rather than a fixture that supplies missing config keys.
    im = InputManager()
    feed(im, 1, eog_h=.9, eog_v=.9, blink=.9)
    assert len(feed(im, im.cfg['remap_window'], eog_h=.3, eog_v=.3, blink=.9)) == 1
    assert im.mode == 'scan'
    changes = feed(im, im.cfg['recover_window'], eog_h=.9, eog_v=.9, blink=.9)
    assert len(changes) == 1 and im.mode == 'wheel'
    assert 'reliable again' in changes[0].reason


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
