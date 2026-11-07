"""Input manager: gestures -> the five commands. THE core differentiator.

Pure logic, no I/O — the hub (ws.py) feeds it events and broadcasts what it returns.
Owner: Role A. Spec: CLAUDE.md "Input manager".

SCAFFOLD STATUS: uses a fixed mapping so the pipeline works end to end.
TODO (Role A, TDD — see tests/test_input_manager.py):
  - rank signals by reliability; split if >=2 gestures with r >= cutoff, else scan
  - preferred mappings: look_left/right -> LEFT/RIGHT; else blink_double/jaw_clench
  - remap when a mapped signal is below cutoff for `remap_window` attempts -> ModeChangeEvent
  - hysteresis: switch back only after `recover_window` attempts >= recover_cutoff
  - debounce duplicate commands within debounce_ms
  - HELP hold-to-confirm (held help_hold_ms or repeated help_repeat_count times)
"""

from dataclasses import dataclass, field

from .config import INPUT
from .models import (
    Command,
    CommandEvent,
    GestureEvent,
    Mode,
    ModeChangeEvent,
    ReliabilityEvent,
    SignalReliabilityEvent,
)

# Gesture -> source that produces it (used to look up reliability).
GESTURE_SOURCE: dict[str, str] = {
    "look_left": "eog_h",
    "look_right": "eog_h",
    "look_up": "eog_v",
    "look_down": "eog_v",
    "blink_double": "blink",
    "jaw_clench": "jaw",
    "jaw_hold": "jaw",
    "brow_raise": "brow",
}


@dataclass
class InputManager:
    cfg: dict = field(default_factory=lambda: dict(INPUT))
    mode: Mode = "split"
    reliability: dict[str, float] = field(default_factory=dict)
    # command -> gesture
    mapping: dict[str, str] = field(
        default_factory=lambda: {
            "LEFT": "look_left",
            "RIGHT": "look_right",
            "SELECT": "jaw_clench",
            "HELP": "jaw_hold",
        }
    )

    def on_gesture(self, ev: GestureEvent) -> list[CommandEvent]:
        """Translate one gesture into zero or more commands."""
        out: list[CommandEvent] = []
        for cmd, gesture in self.mapping.items():
            if gesture == ev.gesture.value:
                out.append(
                    CommandEvent(command=Command(cmd), via=ev.source.value, confidence=ev.confidence, ts=ev.ts)
                )
        return out

    def on_reliability(self, ev: SignalReliabilityEvent) -> list[ReliabilityEvent | ModeChangeEvent]:
        """Update reliability; may return a ModeChangeEvent. Scaffold: just reports state."""
        self.reliability.update(ev.signals)
        return [self.snapshot()]

    def force_mode(self, mode: Mode, reason: str = "manual toggle") -> ModeChangeEvent | None:
        if mode == self.mode:
            return None
        ev = ModeChangeEvent(from_=self.mode, to=mode, reason=reason)
        self.mode = mode
        return ev

    def current_mapping(self) -> dict[str, str]:
        return dict(self.mapping)

    def snapshot(self) -> ReliabilityEvent:
        return ReliabilityEvent(signals=dict(self.reliability), mode=self.mode, mapping=self.current_mapping())
