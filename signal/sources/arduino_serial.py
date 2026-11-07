"""Arduino + BioAmp EXG Pill source.

Reads `t_us,a0,a1,a2` lines at 250000 baud from arduino/relay_exg/relay_exg.ino.
Channel map: A0 = horizontal EOG, A1 = vertical EOG/blinks, A2 = jaw EMG.
Samples go through sources/pipeline.py (filters → detectors → reliability), same as
`run.py --source synthetic --detectors real`.
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


def ArduinoSource(port: str | None, baud: int = 250000):
    if not port:
        raise SystemExit("--port is required for --source arduino (e.g. /dev/tty.usbmodem1101; `ls /dev/tty.usb*`)")
    from sources.pipeline import PipelineSource
    from tools.streams import SerialStream

    return PipelineSource(SerialStream(port, baud))
