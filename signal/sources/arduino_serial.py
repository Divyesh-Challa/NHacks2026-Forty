"""Arduino + BioAmp EXG Pill source. Owner: Role B (Saturday).

Reads `t_us,a0,a1,a2` lines at 115200 baud from arduino/relay_exg/relay_exg.ino.
Channel map: A0 = horizontal EOG, A1 = vertical EOG/blinks, A2 = jaw EMG.
TODO: open serial port (pyserial), parse lines, feed filters -> detectors -> reliability,
yield messages.gesture()/messages.reliability() dicts like SyntheticSource.events().
"""


def parse_line(line: str | bytes) -> tuple[int, int, int, int] | None:
    """One `t_us,a0,a1,a2` line -> ints, or None for partial/garbled lines (common right after connect)."""
    if isinstance(line, bytes):
        line = line.decode("ascii", errors="ignore")
    parts = line.strip().split(",")
    if len(parts) != 4:
        return None
    try:
        t, a0, a1, a2 = (int(p) for p in parts)
    except ValueError:
        return None
    return t, a0, a1, a2


class ArduinoSource:
    def __init__(self, port: str, baud: int = 115200) -> None:
        self.port, self.baud = port, baud

    def degrade(self, signal: str, factor: float) -> None:
        raise NotImplementedError

    async def events(self):
        raise NotImplementedError
        yield  # pragma: no cover
