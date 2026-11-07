"""Input manager tests. Owner: Role A — flip each xfail to a real test (TDD)."""

import pytest

from app.input_manager import InputManager
from app.models import GestureEvent


def gesture(g: str, source: str, ts: int = 0, conf: float = 0.9) -> GestureEvent:
    return GestureEvent(source=source, gesture=g, confidence=conf, ts=ts)


def test_scaffold_maps_look_left_to_left() -> None:
    out = InputManager().on_gesture(gesture("look_left", "eog_h"))
    assert [c.command.value for c in out] == ["LEFT"]


@pytest.mark.xfail(reason="TODO Role A", strict=True)
def test_split_mode_when_two_reliable_gestures() -> None:
    raise NotImplementedError


@pytest.mark.xfail(reason="TODO Role A", strict=True)
def test_scan_mode_when_one_reliable_gesture() -> None:
    raise NotImplementedError


@pytest.mark.xfail(reason="TODO Role A", strict=True)
def test_remap_after_ten_attempts_below_cutoff_emits_mode_change() -> None:
    raise NotImplementedError


@pytest.mark.xfail(reason="TODO Role A", strict=True)
def test_hysteresis_requires_twenty_attempts_above_recover_cutoff() -> None:
    raise NotImplementedError


@pytest.mark.xfail(reason="TODO Role A", strict=True)
def test_debounce_drops_duplicate_within_300ms() -> None:
    raise NotImplementedError


@pytest.mark.xfail(reason="TODO Role A", strict=True)
def test_help_requires_hold_to_confirm() -> None:
    raise NotImplementedError
