"""Arduino + BioAmp EXG Pill source. Owner: Role B (Saturday).

Reads `t_us,a0,a1,a2` lines at 115200 baud from arduino/relay_exg/relay_exg.ino.
Channel map: A0 = horizontal EOG, A1 = vertical EOG/blinks, A2 = jaw EMG.
TODO: open serial port (pyserial), parse lines, feed filters -> detectors -> reliability,
yield messages.gesture()/messages.reliability() dicts like SyntheticSource.events().
"""


class ArduinoSource:
    def __init__(self, port: str, baud: int = 115200) -> None:
        self.port, self.baud = port, baud

    def degrade(self, signal: str, factor: float) -> None:
        raise NotImplementedError

    async def events(self):
        raise NotImplementedError
        yield  # pragma: no cover
