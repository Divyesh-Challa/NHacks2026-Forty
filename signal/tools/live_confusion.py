"""Live confusion test: shuffled prompts (look up/down/left/right, double blink) at a relaxed pace, the
way the wheel is actually used (continuous, not one cued gesture at a time).  Reports, per prompt,
what the detectors emitted, then a confusion matrix, and saves the raw session so it can be replayed.

Close run.py / plot_live first (one program per serial port). Needs `make frontend` for the prompt screen.
Run from the repo root:
  make live-test PORT=/dev/cu.usbmodem1101
or from signal/:
  .venv/bin/python -m tools.live_confusion --port /dev/cu.usbmodem1101 [--reps 6] [--gap 3.5] [--terminal]
Shows the prompts on http://localhost:5173/calibrate (dot + voice) unless --terminal is given.
Uses signal/calibration.json, so calibrate first.
"""
import argparse
import csv
import json
import os
import random
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime

import numpy as np

sys.path.insert(0, os.getcwd())
from detectors import Detection, Pipeline  # noqa: E402
from tools.cue_server import CueServer  # noqa: E402
from tools.streams import open_stream  # noqa: E402

SAY = {
    "look_up": "up",
    "look_down": "down",
    "look_left": "left",
    "look_right": "right",
    "blink_double": "blink twice",
}
p = argparse.ArgumentParser()
p.add_argument("--port", required=True)
p.add_argument("--reps", type=int, default=6)
p.add_argument("--gap", type=float, default=3.5, help="seconds per prompt")
p.add_argument("--terminal", action="store_true", help="no screen: terminal lines and the macOS voice only")
args = p.parse_args()

settings = json.load(open("calibration.json"))["settings"]
pipe = Pipeline(settings=settings)
stream = open_stream("serial", args.port)
cues = None if args.terminal else CueServer()
SEEN = {"look_up": "up", "look_down": "down", "look_left": "left", "look_right": "right", "blink_double": "double blink"}

prompts = list(SAY) * args.reps
random.shuffle(prompts)

rows_all: list[np.ndarray] = []
events: list[tuple[float, str]] = []  # (wall seconds, gesture)
windows: list[tuple[str, float, float]] = []  # (prompt, start, end)
row_marks: list[int] = []  # rows received when each prompt started
row_count = 0


def pump() -> None:
    rows = stream.read()
    global row_count
    if len(rows):
        row_count += len(rows)
        rows_all.append(rows)
        for e in pipe.process(rows):
            if isinstance(e, Detection):
                events.append((time.monotonic(), e.gesture))
                if cues:
                    cues.send(type="seen", text=SEEN.get(e.gesture, e.gesture))


READY_S = 5
if cues:
    print("Open http://localhost:5173/calibrate and press Start…")
    cues.wait_for_start()
    cues.send(type="ready", seconds=READY_S)
    stream.read()  # drop what arrived while waiting
print(f"Starting in {READY_S} s. Look at the target, then return to centre and wait for the next one.")
t_end = time.monotonic() + READY_S
while time.monotonic() < t_end:
    pump()
    time.sleep(0.01)

for n, g in enumerate(prompts):
    start = time.monotonic()
    row_marks.append(row_count)
    print(f"[{n + 1}/{len(prompts)}] NOW: {SAY[g].upper()}", flush=True)
    nxt = prompts[n + 1] if n + 1 < len(prompts) else None
    if cues:
        cues.send(type="cue", gesture=g, seconds=args.gap - 1.2, hold_s=1.0, index=n + 1, total=len(prompts), next=nxt)
    elif sys.platform == "darwin":
        subprocess.Popen(["say", SAY[g]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    sent_rest = False
    while time.monotonic() < start + args.gap:
        pump()
        if cues and not sent_rest and time.monotonic() >= start + args.gap - 1.2:
            cues.send(type="rest", seconds=1.2, next=nxt)
            sent_rest = True
        time.sleep(0.005)
    windows.append((g, start, start + args.gap))

time.sleep(0.5)
pump()

conf: dict[str, Counter] = defaultdict(Counter)
for g, a, b in windows:
    got = [x for ts, x in events if a <= ts < b]
    key = tuple(got) if got else ("(nothing)",)
    conf[g][key] += 1
print()
for g in SAY:
    print(f"{g:13s}", dict(conf[g]))
exact = sum(c[(g,)] for g, c in conf.items())
print(f"\nexactly one correct detection: {exact}/{len(windows)}")

# Save the session (labelled like record.py) for offline replay: a prompt owns the next 2.0 s of rows.
out = f"recordings/live-{datetime.now():%Y%m%d-%H%M%S}.csv"
rows = np.vstack(rows_all)
labels = ["rest"] * len(rows)
for (g, _a, _b), i0 in zip(windows, row_marks):
    for i in range(i0, min(len(rows), i0 + 1000)):
        labels[i] = g
with open(out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["t_us", "a0", "a1", "a2", "label"])
    for r, label in zip(rows, labels):
        w.writerow([*r.tolist(), label])
print("saved", out)
if cues:
    cues.send(type="done")
