"""Raw-sample streams shared by the plotter and recorder: synthetic, serial (Arduino), or CSV replay.

Each stream's read() returns the rows that arrived since the last call as an (n, 4) int array of
t_us, a0, a1, a2 — the Arduino's format.
"""

import threading
import time
from collections import deque

import numpy as np

from config import SIGNAL
from sources.arduino_serial import parse_line
from sources.synthetic import SyntheticEXG

FS = SIGNAL["sample_rate_hz"]


class SyntheticStream:
    def __init__(self, seed: int | None = None) -> None:
        self.exg = SyntheticEXG(seed=seed)
        self.start = time.monotonic()

    def read(self) -> np.ndarray:
        due = int((time.monotonic() - self.start) * FS) - self.exg.n
        return self.exg.chunk(due) if due > 0 else np.empty((0, 4), dtype=np.int64)


class SerialStream:
    def __init__(self, port: str, baud: int = 250000) -> None:
        import serial  # pyserial

        self.ser = serial.Serial(port, baud, timeout=0.1)
        self.buf: deque[tuple[int, int, int, int]] = deque()
        self.lock = threading.Lock()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        while True:
            row = parse_line(self.ser.readline())
            if row:
                with self.lock:
                    self.buf.append(row)

    def read(self) -> np.ndarray:
        with self.lock:
            rows, self.buf = list(self.buf), deque()
        return np.array(rows, dtype=np.int64).reshape(-1, 4)


class CsvStream:
    """Replays a recorded CSV (t_us,a0,a1,a2[,label]) in real time."""

    def __init__(self, path: str) -> None:
        self.rows = np.loadtxt(path, delimiter=",", skiprows=1, usecols=(0, 1, 2, 3), dtype=np.int64)
        self.i = 0
        self.start = time.monotonic()

    def read(self) -> np.ndarray:
        elapsed_us = (time.monotonic() - self.start) * 1e6
        t0 = self.rows[0, 0]
        j = int(np.searchsorted(self.rows[:, 0] - t0, elapsed_us))
        out, self.i = self.rows[self.i : j], j
        return out


def open_stream(source: str, port: str | None = None, path: str | None = None):
    if source == "serial":
        if not port:
            raise SystemExit("--port is required for --source serial (e.g. /dev/tty.usbmodem1101)")
        return SerialStream(port)
    if source == "csv":
        if not path:
            raise SystemExit("--file is required for --source csv")
        return CsvStream(path)
    return SyntheticStream()
