import messages
from reliability import score


def test_gesture_shape() -> None:
    m = messages.gesture("eog_h", "look_left", 0.88, ts=1)
    assert m == {"type": "gesture", "source": "eog_h", "gesture": "look_left", "confidence": 0.88, "ts": 1}


def test_reliability_formula() -> None:
    assert score(0.9, 0.1) == 0.9 * 0.9
