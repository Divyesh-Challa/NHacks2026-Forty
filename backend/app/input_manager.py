"""Input manager: gestures -> the five commands. THE core differentiator.

Pure logic, no I/O — the hub (ws.py) feeds it events and broadcasts what it returns.
Spec: CLAUDE.md "Input manager". Tests: tests/test_input_manager.py.

How it decides:
  - Each signal (eog_h, blink, jaw, ...) is healthy or unhealthy. A reliability reading for a
    signal counts as one attempt. The first reading seeds health (r >= cutoff).
  - healthy -> unhealthy: last `remap_window` readings all below `reliability_cutoff`.
  - unhealthy -> healthy: last `recover_window` readings all >= `recover_cutoff` (hysteresis).
  - Split mode if a preferred LEFT/RIGHT pair is healthy (first match in SPLIT_PAIRS),
    else scan mode with one SELECT gesture from SCAN_SELECT.
  - Scan SELECT is sticky: the current SELECT (including split mode's jaw_clench extra) is kept
    while it is healthy, or while no candidate is. It is re-picked (most reliable healthy
    candidate) only when its signal turns unhealthy and another candidate is healthy, or when
    there is no current SELECT. So it changes only on a health change, never on live values.
  - A mode_change is emitted when the mode or a primary control (LEFT/RIGHT/SELECT) changes.
  - HELP = jaw_hold, which the detector only emits after a sustained (~help_hold_ms) clench,
    so a short clench can never raise HELP. In scan mode HELP is also a scan item.
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
    "jaw_clench": "jaw",
    "jaw_hold": "jaw",
    "brow_raise": "brow",
}

# Split-mode (LEFT, RIGHT) pairs in preference order.
SPLIT_PAIRS: list[tuple[str, str]] = [
    ("look_left", "look_right"),
    ("blink_double", "jaw_clench"),
    ("brow_raise", "jaw_clench"),
]
# Scan-mode SELECT candidates. The current SELECT is kept while it is healthy or while none is;
# otherwise the most reliable healthy candidate is picked.
SCAN_SELECT = ["jaw_clench", "blink_double", "brow_raise", "look_right"]
# Optional split-mode extras, assigned when the gesture is healthy and not already used.
SPLIT_EXTRAS = [("SELECT", "jaw_clench"), ("BACK", "blink_double")]
HELP_GESTURE = "jaw_hold"
PRIMARY = ("LEFT", "RIGHT", "SELECT")

# Sources wired on the 3-pill rig; assumed healthy until their first reading arrives.
DEFAULT_SOURCES = ("eog_h", "eog_v", "blink", "jaw")

SOURCE_NAMES = {
    "eog_h": "eye movement",
    "eog_v": "vertical eye movement",
    "blink": "blinking",
    "jaw": "jaw clench",
    "brow": "eyebrow raise",
}
GESTURE_NAMES = {
    "look_left": "looking left",
    "look_right": "looking right",
    "look_up": "looking up",
    "look_down": "looking down",
    "blink_double": "double blink",
    "jaw_clench": "jaw clench",
    "jaw_hold": "jaw hold",
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
    mode: Mode = "split"
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
        pair = next((p for p in SPLIT_PAIRS if self._ok(p[0]) and self._ok(p[1])), None)

        if mode != "scan" and pair:
            mapping = {"LEFT": pair[0], "RIGHT": pair[1]}
            for cmd, g in SPLIT_EXTRAS:
                if self._ok(g) and g not in mapping.values():
                    mapping[cmd] = g
            if self._ok(HELP_GESTURE):
                mapping["HELP"] = HELP_GESTURE
            return "split", mapping

        if mode == "split":  # forced split with no healthy pair: fall back to eye movement
            return "split", {"LEFT": "look_left", "RIGHT": "look_right"}

        # Sticky SELECT: keep the current one (a split-mode SELECT carries over) while it is healthy,
        # or while nothing is. Health has hysteresis, so live values between the cutoffs never flip it.
        healthy = [g for g in SCAN_SELECT if self._ok(g)]
        current = self.mapping.get("SELECT")
        if current in SCAN_SELECT and (self._ok(current) or not healthy):
            select = current
        else:
            select = max(healthy or SCAN_SELECT, key=lambda g: self.reliability.get(GESTURE_SOURCE[g], 0.0))
        mapping = {"SELECT": select}
        if self._ok(HELP_GESTURE):
            mapping["HELP"] = HELP_GESTURE
        return "scan", mapping

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
            if self.mode == "scan":
                target = f"scan mode with {GESTURE_NAMES[self.mapping['SELECT']]} to select"
            else:
                target = _join([GESTURE_NAMES[self.mapping[k]] for k in ("LEFT", "RIGHT")])
                if self.mapping["LEFT"] == "look_left":
                    target = "eye movement"
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
