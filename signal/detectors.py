"""Threshold gesture detectors with refractory periods. Owner: Role B.

Each detector consumes filtered samples and returns (gesture, confidence) or None.
confidence = how far past threshold the feature is, clipped to [0, 1].
TODO: EogHorizontalDetector (look_left/right), BlinkDetector (blink_double),
JawDetector (jaw_clench / jaw_hold), thresholds set from calibration.
"""

from dataclasses import dataclass


@dataclass
class Detection:
    source: str
    gesture: str
    confidence: float
    ts: int
