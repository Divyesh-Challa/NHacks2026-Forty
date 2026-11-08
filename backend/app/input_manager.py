"""Input manager: gestures -> the five commands. THE core differentiator.

Pure logic, no I/O — the hub (ws.py) feeds it events and broadcasts what it returns.
Spec: CLAUDE.md "Input manager". Tests: tests/test_input_manager.py.

How it decides:
  - Each signal (eog_h, eog_v, blink, ...) is healthy or unhealthy. A reliability reading for a
    signal counts as one attempt. The first reading seeds health (r >= cutoff).
  - healthy -> unhealthy: last `remap_window` readings all below `reliability_cutoff`.
  - unhealthy -> healthy: last `recover_window` readings all >= `recover_cutoff` (hysteresis).
  - Wheel mode (radial wheel, docs/superpowers/specs/2026-11-07-radial-wheel-design.md) if
    horizontal and vertical eye movement are both healthy and a finish gesture is: the four looks
    pick slots and the first healthy WHEEL_FINISH gesture (double blink) = SELECT.
    There is no BACK gesture: looking at the kept slot again goes back.
    Otherwise scan mode with the most reliable healthy gesture as SELECT.
  - A mode_change is emitted when the mode or a primary control (looks/SELECT) changes.
  - HELP is not a gesture. The patient screen has a HELP slot (wheel) / item (scan) that is confirmed
    with SELECT, then the screen sends the alert itself. ACCEPT (centre suggestion) has no gesture
    either: double blink is the finish, so it only comes from the keyboard/mouse simulators.
"""

from collections import deque
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
    "brow_raise": "brow",
}

# Wheel mode: the four looks pick slots.
WHEEL_LOOKS = {"LEFT": "look_left", "RIGHT": "look_right", "UP": "look_up", "DOWN": "look_down"}
# Wheel-mode SELECT (finish / confirm) in preference order; the first healthy one wins.
WHEEL_FINISH = ["blink_double", "brow_raise"]
# Scan-mode SELECT candidates; the most reliable healthy one wins.
SCAN_SELECT = ["blink_double", "brow_raise", "look_right"]
PRIMARY = ("LEFT", "RIGHT", "UP", "DOWN", "SELECT")

# Sources wired on the 2-pill rig; assumed healthy until their first reading arrives.
DEFAULT_SOURCES = ("eog_h", "eog_v", "blink")

SOURCE_NAMES = {
    "eog_h": "eye movement",
    "eog_v": "vertical eye movement",
    "blink": "blinking",
    "brow": "eyebrow raise",
}
GESTURE_NAMES = {
    "look_left": "looking left",
    "look_right": "looking right",
    "look_up": "looking up",
    "look_down": "looking down",
    "blink_double": "double blink",
    "brow_raise": "eyebrow raise",
}


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


@dataclass
class InputManager:
    cfg: dict = field(default_factory=lambda: dict(INPUT))
    reliability: dict[str, float] = field(default_factory=dict)
    healthy: dict[str, bool] = field(default_factory=lambda: {s: True for s in DEFAULT_SOURCES})
    override: Mode | None = None  # manual mode toggle (keyboard sim)
    mode: Mode = "wheel"
    mapping: dict[str, str] = field(default_factory=dict)  # command -> gesture
    _history: dict[str, deque[float]] = field(default_factory=dict)
    _last_emit: dict[str, int] = field(default_factory=dict)  # command -> ts of last emit

    def __post_init__(self) -> None:
        self.mode, self.mapping = self._choose()

    # --- events in ---

    def on_gesture(self, ev: GestureEvent) -> list[CommandEvent]:
        """Translate one gesture into zero or more commands (debounced per command)."""
        out: list[CommandEvent] = []
        for cmd, gesture in self.mapping.items():
            if gesture != ev.gesture.value:
                continue
            last = self._last_emit.get(cmd)
            if last is not None and 0 <= ev.ts - last < self.cfg["debounce_ms"]:
                continue
            self._last_emit[cmd] = ev.ts
            out.append(CommandEvent(command=Command(cmd), via=ev.source.value, confidence=ev.confidence, ts=ev.ts))
        return out

    def on_reliability(self, ev: SignalReliabilityEvent) -> list[ReliabilityEvent | ModeChangeEvent]:
        """Record readings, update per-signal health, remap if needed."""
        self.reliability.update(ev.signals)
        lost: list[str] = []
        regained: list[str] = []
        for source, r in ev.signals.items():
            hist = self._history.setdefault(
                source, deque(maxlen=max(self.cfg["remap_window"], self.cfg["recover_window"]))
            )
            first = not hist
            hist.append(r)
            if first:
                self.healthy[source] = r >= self.cfg["reliability_cutoff"]
            elif self.healthy.get(source, False) and self._all_last(hist, self.cfg["remap_window"], below=True):
                self.healthy[source] = False
                lost.append(source)
            elif not self.healthy.get(source, False) and self._all_last(hist, self.cfg["recover_window"], below=False):
                self.healthy[source] = True
                regained.append(source)

        out: list[ReliabilityEvent | ModeChangeEvent] = []
        change = self._apply(self._reason(lost, regained))
        if change:
            out.append(change)
        out.append(self.snapshot())
        return out

    def force_mode(self, mode: Mode, reason: str | None = None) -> ModeChangeEvent | None:
        if mode == self.mode:
            return None
        self.override = mode
        auto_mode, _ = self._choose(use_override=False)
        if auto_mode == mode:
            self.override = None
        return self._apply(lambda: reason or f"Switched to {mode} mode by hand (testing).")

    # --- state out ---

    def current_mapping(self) -> dict[str, str]:
        return dict(self.mapping)

    def snapshot(self) -> ReliabilityEvent:
        return ReliabilityEvent(signals=dict(self.reliability), mode=self.mode, mapping=self.current_mapping())

    # --- internals ---

    def _all_last(self, hist: deque[float], n: int, below: bool) -> bool:
        if len(hist) < n:
            return False
        recent = list(hist)[-n:]
        if below:
            return all(r < self.cfg["reliability_cutoff"] for r in recent)
        return all(r >= self.cfg["recover_cutoff"] for r in recent)

    def _ok(self, gesture: str) -> bool:
        return self.healthy.get(GESTURE_SOURCE[gesture], False)

    def _choose(self, use_override: bool = True) -> tuple[Mode, dict[str, str]]:
        mode = self.override if use_override else None
        eyes = all(self._ok(g) for g in WHEEL_LOOKS.values())
        finish = next((g for g in WHEEL_FINISH if self._ok(g)), None)

        if mode != "scan" and eyes and finish:
            return "wheel", {**WHEEL_LOOKS, "SELECT": finish}

        if mode == "wheel":  # forced wheel without healthy eyes: fall back to the default mapping
            return "wheel", {**WHEEL_LOOKS, "SELECT": WHEEL_FINISH[0]}

        candidates = [g for g in SCAN_SELECT if self._ok(g)] or SCAN_SELECT
        select = max(candidates, key=lambda g: self.reliability.get(GESTURE_SOURCE[g], 0.0))
        return "scan", {"SELECT": select}

    def _apply(self, reason) -> ModeChangeEvent | None:
        """Recompute mode/mapping; return a ModeChangeEvent if anything primary changed."""
        old_mode, old_mapping = self.mode, self.mapping
        self.mode, self.mapping = self._choose()
        changed = self.mode != old_mode or any(old_mapping.get(k) != self.mapping.get(k) for k in PRIMARY)
        if not changed:
            return None
        return ModeChangeEvent(from_=old_mode, to=self.mode, reason=reason())

    def _reason(self, lost: list[str], regained: list[str]):
        def build() -> str:
            select = GESTURE_NAMES[self.mapping["SELECT"]]
            if self.mode == "scan":
                target = f"scan mode with {select} to select"
            else:
                target = f"eye movement with {select} to finish"
            if lost:
                cutoff = f"{self.cfg['reliability_cutoff']:.0%}"
                who = _join([SOURCE_NAMES.get(s, s) for s in lost])
                return f"{who[0].upper() + who[1:]} reliability fell below {cutoff}. Switching to {target}."
            if regained:
                who = _join([SOURCE_NAMES.get(s, s) for s in regained])
                verb = "is" if len(regained) == 1 else "are"
                return f"{who[0].upper() + who[1:]} {verb} reliable again. Switching back to {target}."
            return f"Switching to {target}."

        return build
