import messages
from reliability import score


def test_gesture_shape() -> None:
    m = messages.gesture("eog_h", "look_left", 0.88, ts=1)
    assert m == {"type": "gesture", "source": "eog_h", "gesture": "look_left", "confidence": 0.88, "ts": 1}


def test_reliability_formula() -> None:
    assert score(0.9, 0.1) == 0.9 * 0.9


def test_parse_line_handles_garbage() -> None:
    from sources.arduino_serial import parse_line

    assert parse_line(b"1000,512,500\r\n") == (1000, 512, 500)
    assert parse_line("12,5") is None
    assert parse_line(b"\xff\xfe1,2,3,x") is None
