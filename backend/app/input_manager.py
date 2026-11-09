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
    Otherwise scan mode with one SELECT gesture from SCAN_SELECT.
  - Scan SELECT is sticky: the current SELECT (a wheel-mode finish carries over) is kept while it
    is healthy, or while no candidate is. It is re-picked (most reliable healthy candidate) only
    when its signal turns unhealthy and another candidate is healthy, or when there is no current
    SELECT. So it changes only on a health change, never on live values.
  - A mode_change is emitted when the mode or a primary control (looks/SELECT) changes.
  - Merge window: when a health change would move a primary control while another mapping signal
    is part-way through its own health-changing run (healthy with a run below `reliability_cutoff`
    that can reach `remap_window`, or unhealthy with a run at/above `recover_cutoff` that can reach
    `recover_window`, before `merge_window` readings have passed), the remap is held. It lands when
    that run completes (and joins the banner), when the run breaks, or when the window ends. So the
    eye degrade (eog_h and eog_v failing a few readings apart) gives one wheel -> scan banner naming
    both, while a lone loss, or one next to a signal steadily hovering between the cutoffs, is
    applied at once. A hold lasts at most 12 readings (`merge_window`); at most 9 when the only run
    being waited on is a loss (a run already under way finishes within `remap_window` - 1 more
    readings; a pending regain run, or another run starting later, can keep it open up to 12).
    The health rule itself is never delayed; while held, the old mode and mapping stay.
    Readings (reliability events) are the clock.
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
# Scan-mode SELECT candidates. The current SELECT is kept while it is healthy or while none is;
# otherwise the most reliable healthy candidate is picked.
SCAN_SELECT = ["blink_double", "brow_raise", "look_right"]
PRIMARY = ("LEFT", "RIGHT", "UP", "DOWN", "SELECT")
# Sources that some mapping can use (eog_h, eog_v, blink, brow); only these can hold a remap open.
MAPPING_SOURCES = {GESTURE_SOURCE[g] for g in [*WHEEL_LOOKS.values(), *WHEEL_FINISH, *SCAN_SELECT]}

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


def _source_order(source: str) -> int:
    return list(SOURCE_NAMES).index(source) if source in SOURCE_NAMES else len(SOURCE_NAMES)


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
    _readings: int = 0  # reliability events seen: the merge window's clock
    _held_since: int | None = None  # reading that started a held remap
    # Health losses/regains not yet named in a banner: source -> reading it happened at.
    _lost: dict[str, int] = field(default_factory=dict)
    _regained: dict[str, int] = field(default_factory=dict)

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
        """Record readings, update per-signal health, remap if needed (possibly held, see docstring)."""
        self.reliability.update(ev.signals)
        self._readings += 1
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

        # Only changes inside the window can join a banner (a held remap never outlives it).
        for pending in (self._lost, self._regained):
            for s in [s for s, at in pending.items() if self._readings - at > self.cfg["merge_window"]]:
                del pending[s]
        for s in lost:
            self._regained.pop(s, None)
            self._lost[s] = self._readings
        for s in regained:
            self._lost.pop(s, None)
            self._regained[s] = self._readings

        out: list[ReliabilityEvent | ModeChangeEvent] = []
        if self._held_since is None and (lost or regained) and self._would_change() and self._settling():
            self._held_since = self._readings
        if self._held_since is None or not self._settling():  # held: the board keeps its mapping
            change = self._apply(self._reason())
            if change:
                out.append(change)
        out.append(self.snapshot())
        return out

    @property
    def remap_held(self) -> bool:
        """A primary remap is waiting for the merge window (the board still shows the old mapping)."""
        return self._held_since is not None

    def force_mode(self, mode: Mode, reason: str | None = None) -> ModeChangeEvent | None:
        """Manual mode toggle. Asking for the current mode lands a held remap (with its own reason).

        That request leaves `override` alone: pinning the current mode could hold the board on a
        dead mapping (e.g. wheel on failed eyes when the held remap is to double-blink scan).
        """
        if mode == self.mode:
            return self._apply(self._reason()) if self.remap_held else None
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

        # Sticky SELECT: keep the current one (a wheel-mode finish carries over) while it is healthy,
        # or while nothing is. Health has hysteresis, so live values between the cutoffs never flip it.
        healthy = [g for g in SCAN_SELECT if self._ok(g)]
        current = self.mapping.get("SELECT")
        if current in SCAN_SELECT and (self._ok(current) or not healthy):
            select = current
        else:
            select = max(healthy or SCAN_SELECT, key=lambda g: self.reliability.get(GESTURE_SOURCE[g], 0.0))
        return "scan", {"SELECT": select}

    def _changes_primary(self, mode: Mode, mapping: dict[str, str]) -> bool:
        return mode != self.mode or any(self.mapping.get(k) != mapping.get(k) for k in PRIMARY)

    def _would_change(self) -> bool:
        return self._changes_primary(*self._choose())

    def _run(self, source: str, below: bool) -> int:
        """Length of the source's current run of readings below cutoff (below) or >= recover_cutoff."""
        n = 0
        for r in reversed(self._history.get(source, ())):
            if (r < self.cfg["reliability_cutoff"]) if below else (r >= self.cfg["recover_cutoff"]):
                n += 1
            else:
                break
        return n

    def _settling(self) -> bool:
        """Another mapping signal is part-way through a run that can change its health within the window.

        After a loss: a healthy signal with a run below `reliability_cutoff` that can reach
        `remap_window`. After a regain: an unhealthy signal with a run at/above `recover_cutoff`
        that can reach `recover_window`. A hover between the cutoffs is no run, so it holds nothing.
        """
        start = self._readings if self._held_since is None else self._held_since
        left = start + self.cfg["merge_window"] - self._readings  # readings still inside the window
        pending = set(self._lost) | set(self._regained)
        for s in MAPPING_SOURCES - pending:
            if self.healthy.get(s, False):
                k = self._run(s, below=True)
                if self._lost and k and self.cfg["remap_window"] - k <= left:
                    return True
            else:
                k = self._run(s, below=False)
                if self._regained and k and self.cfg["recover_window"] - k <= left:
                    return True
        return False

    def _apply(self, reason) -> ModeChangeEvent | None:
        """Recompute mode/mapping; return a ModeChangeEvent if anything primary changed.

        Ends any held remap. Pending losses/regains are kept until a banner names them, so a loss
        that changed nothing primary (e.g. brow while blink is the finish) is named by a remap that
        follows inside the window.
        """
        self._held_since = None
        mode, mapping = self._choose()
        changed = self._changes_primary(mode, mapping)
        old_mode = self.mode
        self.mode, self.mapping = mode, mapping
        if not changed:
            return None
        event = ModeChangeEvent(from_=old_mode, to=self.mode, reason=reason())
        self._lost, self._regained = {}, {}
        return event

    def _reason(self):
        lost = sorted(self._lost, key=_source_order)
        regained = sorted(self._regained, key=_source_order)

        def build() -> str:
            select = GESTURE_NAMES[self.mapping["SELECT"]]
            if self.mode == "scan":
                target = f"scan mode with {select} to select"
            else:
                target = f"eye movement with {select} to finish"
            fell = back = ""
            if lost:
                fell = f"{_join([SOURCE_NAMES.get(s, s) for s in lost])} reliability fell below "
                fell += f"{self.cfg['reliability_cutoff']:.0%}"
            if regained:
                back = f"{_join([SOURCE_NAMES.get(s, s) for s in regained])} "
                back += f"{'is' if len(regained) == 1 else 'are'} reliable again"
            if fell and back:
                why, switch = f"{fell} and {back}", "Switching to"
            elif fell or back:
                why, switch = fell or back, "Switching to" if fell else "Switching back to"
            else:
                return f"Switching to {target}."
            return f"{why[0].upper() + why[1:]}. {switch} {target}."

        return build
