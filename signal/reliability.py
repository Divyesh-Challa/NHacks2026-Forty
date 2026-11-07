"""Live per-signal reliability. Owner: Role B.

r = accuracy * (1 - false_trigger_rate) over a rolling window.
TODO: seed from calibration; update from usage (a BACK right after a selection = likely error).
"""


def score(accuracy: float, false_trigger_rate: float) -> float:
    return max(0.0, min(1.0, accuracy * (1.0 - false_trigger_rate)))
