"""Record a labelled session: prompts each gesture in turn and writes t_us,a0,a1,a2,label.

  python -m tools.record --source serial --port /dev/tty.usbmodem1101 --reps 10
  python -m tools.record --source synthetic --reps 3          # dry run; performs the prompts itself

Each prompt gets a window labelled with the gesture (2 s); the gaps are
labelled "rest". calibration.py uses the same protocol, and can calibrate from these CSVs offline.
"""

import argparse
import csv
import random
import time
from datetime import datetime
from pathlib import Path

from tools.cue_server import CueServer
from tools.streams import SyntheticStream, open_stream

GESTURES = ["look_left", "look_right", "blink_double"]
VERTICAL = ["look_up", "look_down"]  # hardware sessions only: synthetic dry runs keep the left/right/blink set
PROMPT_S = 2.0
REST_S = 2.0
OUT_DIR = Path(__file__).resolve().parents[1] / "recordings"
INSTRUCTIONS = {
    "look_left": "LOOK LEFT, then back to centre",
    "look_right": "LOOK RIGHT, then back to centre",
    "look_up": "LOOK UP and hold for a second, then back to centre",
    "look_down": "LOOK DOWN and hold for a second, then back to centre",
    "blink_double": "DOUBLE BLINK",
}


def prompt_seconds(gesture: str) -> float:
    return PROMPT_S


def prompts_for(reps: int, rng=random, vertical: bool = False) -> list[str]:
    prompts = (GESTURES + (VERTICAL if vertical else [])) * reps
    rng.shuffle(prompts)
    return prompts


READY_S = 3.0  # on-screen "get ready" before recording starts, so settling isn't counted as rest
HOLD_S = 1.2  # cue page: the dot stays at the side this long, then returns to centre


def record(stream, reps: int, rest: float = 20.0, out: Path | None = None, cues=None) -> Path:
    """cues: optional tools.cue_server.CueServer. The /calibrate page then shows and speaks every prompt."""
    OUT_DIR.mkdir(exist_ok=True)
    out = out or OUT_DIR / f"session-{datetime.now():%Y%m%d-%H%M%S}.csv"
    prompts = prompts_for(reps, vertical=not isinstance(stream, SyntheticStream))

    def cue(**msg) -> None:
        if cues:
            cues.send(**msg)

    if cues:
        print("Open http://localhost:5173/calibrate and press Start…")
        cues.wait_for_start()
        cue(type="ready", seconds=READY_S)
        time.sleep(READY_S)
        stream.read()  # drop what arrived while getting ready
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
        cue(type="intro", seconds=rest)
        capture(rest, "rest")
        for i, gesture in enumerate(prompts, 1):
            print(f"[{i}/{len(prompts)}]  ➜  {INSTRUCTIONS[gesture]}")
            nxt = prompts[i] if i < len(prompts) else None
            cue(type="cue", gesture=gesture, seconds=prompt_seconds(gesture), hold_s=HOLD_S, index=i, total=len(prompts), next=nxt)
            if isinstance(stream, SyntheticStream):
                stream.exg.trigger(gesture, delay_s=0.3)  # dry run: simulate a reaction time
            capture(prompt_seconds(gesture), gesture)
            cue(type="rest", seconds=REST_S, next=nxt)
            capture(REST_S, "rest")
        cue(type="done")
    print(f"Done: {out}")
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--source", choices=["synthetic", "serial"], default="synthetic")
    p.add_argument("--port")
    p.add_argument("--reps", type=int, default=10, help="prompts per gesture")
    p.add_argument("--rest", type=float, default=20.0, help="seconds of rest recorded at the start")
    p.add_argument("--out")
    p.add_argument("--cue", action="store_true", help="drive the /calibrate page (dot + voice) instead of terminal prompts")
    args = p.parse_args()
    cues = CueServer() if args.cue else None
    record(open_stream(args.source, args.port), args.reps, args.rest, Path(args.out) if args.out else None, cues)


if __name__ == "__main__":
    main()
