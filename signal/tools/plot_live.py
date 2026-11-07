"""Live plot of the three EXG channels — for electrode placement and threshold tuning.

  python -m tools.plot_live                                   # synthetic
  python -m tools.plot_live --source serial --port /dev/tty.usbmodem1101
  python -m tools.plot_live --source csv --file recordings/session.csv

Synthetic keys (click the plot window first): l/r look, b blink, j clench, h hold, d degrade eyes, u restore.
"""

import argparse
from collections import deque

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation

from tools.streams import FS, SyntheticStream, open_stream

WINDOW_S = 5
LABELS = ["A0 · horizontal EOG", "A1 · vertical EOG / blink", "A2 · jaw EMG"]
KEYS = {"l": "look_left", "r": "look_right", "b": "blink_double", "j": "jaw_clench", "h": "jaw_hold"}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--source", choices=["synthetic", "serial", "csv"], default="synthetic")
    p.add_argument("--port")
    p.add_argument("--file")
    args = p.parse_args()
    stream = open_stream(args.source, args.port, args.file)

    n = WINDOW_S * FS
    data = [deque([512] * n, maxlen=n) for _ in range(3)]
    t = np.linspace(-WINDOW_S, 0, n)

    fig, axes = plt.subplots(3, 1, sharex=True, figsize=(10, 7))
    fig.canvas.manager.set_window_title("Relay — live EXG")
    lines = []
    for ax, label in zip(axes, LABELS):
        (line,) = ax.plot(t, list(data[0]), lw=1)
        ax.set_ylabel(label, fontsize=9)
        ax.grid(alpha=0.3)
        lines.append(line)
    axes[-1].set_xlabel("seconds")
    status = fig.text(0.01, 0.01, "", fontsize=9)

    if isinstance(stream, SyntheticStream):
        status.set_text("keys: l/r look · b blink · j clench · h hold · d degrade eyes · u restore")

        def on_key(event) -> None:
            if event.key in KEYS:
                stream.exg.trigger(KEYS[event.key])
            elif event.key == "d":
                stream.exg.degrade("eye", 0.3)
            elif event.key == "u":
                stream.exg.degrade("eye", 1.0)
                stream.exg.degrade("jaw", 1.0)

        fig.canvas.mpl_connect("key_press_event", on_key)

    def update(_frame):
        rows = stream.read()
        for ch in range(3):
            data[ch].extend(rows[:, ch + 1].tolist())
        for ch, (ax, line) in enumerate(zip(axes, lines)):
            y = np.fromiter(data[ch], dtype=float, count=n)
            line.set_ydata(y)
            lo, hi = y.min(), y.max()
            pad = max(10.0, (hi - lo) * 0.1)
            ax.set_ylim(lo - pad, hi + pad)
        return lines

    _anim = FuncAnimation(fig, update, interval=33, cache_frame_data=False)  # noqa: F841 (keep a reference)
    plt.tight_layout(rect=(0, 0.03, 1, 1))
    plt.show()


if __name__ == "__main__":
    main()
