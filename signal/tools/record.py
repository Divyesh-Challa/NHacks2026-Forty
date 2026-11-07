"""Record a labelled session: prompts each gesture in turn and writes t_us,a0,a1,a2,label.

  python -m tools.record --source serial --port /dev/tty.usbmodem1101 --reps 10
  python -m tools.record --source synthetic --reps 3          # dry run; performs the prompts itself

Each prompt gets a window labelled with the gesture (2 s; 3.5 s for the HELP hold); the gaps are
labelled "rest". calibration.py uses the same protocol, and can calibrate from these CSVs offline.
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
HOLD_PROMPT_S = 3.5  # jaw_hold needs help_hold_ms (2 s) plus reaction time
REST_S = 2.0
OUT_DIR = Path(__file__).resolve().parents[1] / "recordings"
INSTRUCTIONS = {
    "look_left": "LOOK LEFT, then back to centre",
    "look_right": "LOOK RIGHT, then back to centre",
    "blink_double": "DOUBLE BLINK",
    "jaw_clench": "CLENCH your jaw briefly",
    "jaw_hold": "HOLD a jaw clench until the next prompt",
}


def prompt_seconds(gesture: str) -> float:
    return HOLD_PROMPT_S if gesture == "jaw_hold" else PROMPT_S


def prompts_for(reps: int, rng=random) -> list[str]:
    prompts = GESTURES * reps + ["jaw_hold"] * max(2, reps // 4)
    rng.shuffle(prompts)
    return prompts


def record(stream, reps: int, rest: float = 20.0, out: Path | None = None) -> Path:
    OUT_DIR.mkdir(exist_ok=True)
    out = out or OUT_DIR / f"session-{datetime.now():%Y%m%d-%H%M%S}.csv"
    prompts = prompts_for(reps)
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_us", "a0", "a1", "a2", "label"])

        def capture(seconds: float, label: str) -> None:
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                for row in stream.read():
                    w.writerow([*row.tolist(), label])
                time.sleep(0.02)

        print(f"Recording to {out}\nRelax and look straight ahead for {rest:.0f} s…")
        capture(rest, "rest")
        for i, gesture in enumerate(prompts, 1):
            print(f"[{i}/{len(prompts)}]  ➜  {INSTRUCTIONS[gesture]}")
            if isinstance(stream, SyntheticStream):
                stream.exg.trigger(gesture, delay_s=0.3)  # dry run: simulate a reaction time
            capture(prompt_seconds(gesture), gesture)
            capture(REST_S, "rest")
    print(f"Done: {out}")
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--source", choices=["synthetic", "serial"], default="synthetic")
    p.add_argument("--port")
    p.add_argument("--reps", type=int, default=10, help="prompts per gesture")
    p.add_argument("--rest", type=float, default=20.0, help="seconds of rest recorded at the start")
    p.add_argument("--out")
    args = p.parse_args()
    record(open_stream(args.source, args.port), args.reps, args.rest, Path(args.out) if args.out else None)


if __name__ == "__main__":
    main()
