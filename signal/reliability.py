"""Live per-signal reliability.

    r = accuracy × (1 − false_trigger_rate)

- accuracy: share of the last `attempt_window` gesture attempts that were detected
- false_trigger_rate: share of the last `rest_window` rest seconds with a spurious detection

Windows are pre-filled from calibration (seed()), so a fresh signal starts at its calibrated
reliability and real outcomes roll the seed out. Usage feedback (record_error, e.g. a BACK right
after a selection) counts as a missed attempt.

The backend's input manager decides what to do with these numbers (remap below 0.6 for 10
readings, recover at ≥ 0.75 for 20) — this module only measures.
"""

from collections import deque
from dataclasses import dataclass, field

from config import SIGNAL


def score(accuracy: float, false_trigger_rate: float) -> float:
    return max(0.0, min(1.0, accuracy * (1.0 - false_trigger_rate)))


def _fill(n: int, share: float) -> list[bool]:
    k = round(share * n)
    # Spread the True values evenly so the seed rolls out smoothly.
    return [((i + 1) * k) // n > (i * k) // n for i in range(n)]


@dataclass
class _Stats:
    attempts: deque[bool]  # True = detected
    rests: deque[bool]  # True = false trigger


@dataclass
class ReliabilityTracker:
    attempt_window: int = SIGNAL["attempt_window"]
    rest_window: int = SIGNAL["rest_window"]
    default_accuracy: float = SIGNAL["default_accuracy"]
    default_false_trigger_rate: float = SIGNAL["default_false_trigger_rate"]
    _stats: dict[str, _Stats] = field(default_factory=dict)

    def seed(self, signal: str, accuracy: float, false_trigger_rate: float) -> None:
        """Start a signal from calibration results (replaces any history)."""
        self._stats[signal] = _Stats(
            attempts=deque(_fill(self.attempt_window, accuracy), maxlen=self.attempt_window),
            rests=deque(_fill(self.rest_window, false_trigger_rate), maxlen=self.rest_window),
        )

    def _get(self, signal: str) -> _Stats:
        if signal not in self._stats:
            self.seed(signal, self.default_accuracy, self.default_false_trigger_rate)
        return self._stats[signal]

    def record_attempt(self, signal: str, detected: bool) -> None:
        self._get(signal).attempts.append(detected)

    def record_rest(self, signal: str, false_trigger: bool) -> None:
        self._get(signal).rests.append(false_trigger)

    def record_error(self, signal: str) -> None:
        """Usage feedback: a detection the user immediately undid counts as a miss."""
        self.record_attempt(signal, False)

    def accuracy(self, signal: str) -> float:
        a = self._get(signal).attempts
        return sum(a) / len(a)

    def false_trigger_rate(self, signal: str) -> float:
        r = self._get(signal).rests
        return sum(r) / len(r)

    def score(self, signal: str) -> float:
        return score(self.accuracy(signal), self.false_trigger_rate(signal))

    def snapshot(self, signals: list[str] | None = None) -> dict[str, float]:
        return {s: round(self.score(s), 3) for s in (signals or list(self._stats))}
