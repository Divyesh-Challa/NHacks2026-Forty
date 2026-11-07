"""Record a labelled session: prompts each gesture in turn and writes t_us,a0,a1,a2,label.

  python -m tools.record --source serial --port /dev/tty.usbmodem1101 --reps 10
  python -m tools.record --source synthetic --reps 3          # dry run; performs the prompts itself

Each prompt gets a `PROMPT_S`-second window labelled with the gesture; the gaps are labelled "rest".
Detector tests and calibration can then be run offline on the CSV (see tests in signal/tests/).
"""

import argparse
import csv
import random
import time
from datetime import datetime
from pathlib import Path

from tools.streams import SyntheticStream, open_stream

GESTURES = ["look_left", "look_right", "blink_double", "jaw_clench"]
PROMPT_S = 2.0
REST_S = 2.0
OUT_DIR = Path(__file__).resolve().parents[1] / "recordings"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--source", choices=["synthetic", "serial"], default="synthetic")
    p.add_argument("--port")
    p.add_argument("--reps", type=int, default=10, help="prompts per gesture")
    p.add_argument("--rest", type=float, default=20.0, help="seconds of rest recorded at the start")
    p.add_argument("--out")
    args = p.parse_args()

    stream = open_stream(args.source, args.port)
    prompts = GESTURES * args.reps
    random.shuffle(prompts)
    OUT_DIR.mkdir(exist_ok=True)
    out = Path(args.out) if args.out else OUT_DIR / f"session-{datetime.now():%Y%m%d-%H%M%S}.csv"

    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_us", "a0", "a1", "a2", "label"])

        def capture(seconds: float, label: str) -> None:
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                for row in stream.read():
                    w.writerow([*row.tolist(), label])
                time.sleep(0.02)

        print(f"Recording to {out}\nRelax and look straight ahead for {args.rest:.0f} s…")
        capture(args.rest, "rest")
        for i, gesture in enumerate(prompts, 1):
            print(f"[{i}/{len(prompts)}]  ➜  {gesture.replace('_', ' ').upper()} now")
            if isinstance(stream, SyntheticStream):
                stream.exg.trigger(gesture, delay_s=0.3)  # dry run: simulate a reaction time
            capture(PROMPT_S, gesture)
            capture(REST_S, "rest")
    print(f"Done: {out}")


if __name__ == "__main__":
    main()
