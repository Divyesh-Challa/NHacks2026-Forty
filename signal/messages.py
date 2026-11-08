"""Builds the JSON sent to the backend on /ws/signal.

Mirrors backend/app/models.py (GestureEvent, SignalReliabilityEvent) — keep in sync.
"""

import time

SOURCES = {"eog_h", "eog_v", "blink", "brow", "sim"}
GESTURES = {"look_left", "look_right", "look_up", "look_down", "blink_double", "brow_raise"}


def now_ms() -> int:
    return int(time.time() * 1000)


def gesture(source: str, name: str, confidence: float, ts: int | None = None) -> dict:
    assert source in SOURCES and name in GESTURES, (source, name)
    return {"type": "gesture", "source": source, "gesture": name, "confidence": round(confidence, 3), "ts": ts or now_ms()}


def reliability(signals: dict[str, float], ts: int | None = None) -> dict:
    return {"type": "reliability", "signals": {k: round(v, 3) for k, v in signals.items()}, "ts": ts or now_ms()}
