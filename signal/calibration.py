"""Guided calibration: prompts → per-user thresholds + per-signal accuracy and false-trigger rate.

  python calibration.py --source serial --port /dev/tty.usbmodem1101    # with electrodes (~3 min)
  python calibration.py --file recordings/session-….csv                 # offline, from tools.record
  python calibration.py --source synthetic                              # instant dry run

Protocol (tools/record.py): 20 s rest, then shuffled prompts (look left/right, double blink,
clench ×reps; hold ×reps/4), each in a fixed window followed by 2 s rest.

From the recording:
  1. amplitude per signal = median peak of the filtered feature inside its prompt windows
     (EOG relative to the half-second before the prompt; polarity of A0 detected from look_left)
  2. noise per signal = typical peak in 1 s rest chunks
  3. threshold = max(50% of amplitude, 2× noise); floor (near-miss) = max(25% of amplitude, 1.3× noise)
  4. run the real Pipeline with those settings over the whole recording:
       accuracy = prompts where the right gesture was detected in time / prompts
       false-trigger rate = rest seconds with any detection of that signal / rest seconds
These numbers seed live reliability, get POSTed to the backend, and are the ones we quote in the
pitch. They're measured on the same data the thresholds came from, so treat them as optimistic.
"""

import argparse
import csv
import json
import urllib.request
from datetime import datetime
from pathlib import Path

import numpy as np

from config import BACKEND_WS_URL, DETECTORS
from detectors import Detection, Pipeline
from filters import FS
from reliability import score

HERE = Path(__file__).resolve().parent
CAL_PATH = HERE / "calibration.json"
SIGNAL_GESTURES = {
    "eog_h": ["look_left", "look_right"],
    "eog_v": ["look_down", "look_up"],  # only scored if the recording has these prompts (hardware sessions)
    "blink": ["blink_double"],
}
MATCH_SLACK_US = 800_000  # a detection up to this long after the window still counts 
REST_SKIP_US = 1_000_000  # ignore the first second of rest after a prompt (eyes returning, late release)


def segments(t_us: np.ndarray, labels: list[str]) -> list[tuple[str, int, int]]:
    """Per-row labels → contiguous (label, start_us, end_us) runs."""
    out: list[tuple[str, int, int]] = []
    start = 0
    for i in range(1, len(labels) + 1):
        if i == len(labels) or labels[i] != labels[start]:
            out.append((labels[start], int(t_us[start]), int(t_us[i - 1])))
            start = i
    return out


def _window(t: np.ndarray, a: int, b: int) -> slice:
    return slice(int(np.searchsorted(t, a)), int(np.searchsorted(t, b, side="right")))


def measure(rows: np.ndarray, labels: list[str], fs: float = FS) -> dict:
    """Amplitudes and rest noise of each feature, before any thresholds."""
    t = rows[:, 0]
    h, v = Pipeline(fs).features(rows)
    segs = segments(t, labels)
    pre = int(0.5 * 1e6)
    eog: dict[str, list[float]] = {"look_left": [], "look_right": []}
    vert: dict[str, list[float]] = {"look_down": [], "look_up": []}
    blink: list[float] = []
    for label, a, b in segs:
        w, p = _window(t, a, b), _window(t, a - pre, a)
        if label in eog and p.stop > p.start:
            d = h[w] - np.median(h[p])
            eog[label].append(float(d[np.argmax(np.abs(d))]))
        elif label in vert and p.stop > p.start:
            d = v[w] - np.median(v[p])
            vert[label].append(float(d[np.argmax(np.abs(d))]))
        elif label == "blink_double" and p.stop > p.start:
            blink.append(float(np.max(v[w] - np.median(v[p]))))

    rest_h, rest_v, rest_va = [], [], []
    for label, a, b in segs:
        if label != "rest":
            continue
        a = a if a == segs[0][1] else a + REST_SKIP_US
        for c in range(a, b - 1_000_000 + 1, 1_000_000):
            w = _window(t, c, c + 1_000_000)
            rest_h.append(float(np.max(np.abs(h[w] - np.median(h[w])))))
            rest_v.append(float(np.max(v[w] - np.median(v[w]))))
            rest_va.append(float(np.max(np.abs(v[w] - np.median(v[w])))))

    lefts = eog["look_left"]
    invert = bool(lefts) and float(np.median(lefts)) > 0  # look_left should read negative
    eog_amps = [abs(x) for x in eog["look_left"] + eog["look_right"]]
    ups = vert["look_up"]
    vert_invert = bool(ups) and float(np.median(ups)) < 0  # look_up should read positive
    vert_amps = [abs(x) for x in vert["look_down"] + ups]
    pct = lambda xs, q: float(np.percentile(xs, q)) if xs else 0.0  # noqa: E731
    return {
        "eog_invert": False,
        "vert_invert": vert_invert,
        "amplitude": {
            "eog_h": float(np.median(eog_amps)) if eog_amps else None,
            "eog_v": float(np.median(vert_amps)) if vert_amps else None,
            "blink": float(np.median(blink)) if blink else None,
        },
        # Rest blinks are real blinks, so blink noise uses the median chunk, not the tail.
        # Rest blinks hit A1 too, so vertical noise is the median chunk like blink; a look must also outlast a blink.
        "noise": {"eog_h": pct(rest_h, 90), "eog_v": pct(rest_va, 50), "blink": pct(rest_v, 50)},
    }


def thresholds(m: dict) -> dict:
    """Detector settings from measured amplitudes (keeps the defaults for anything not measured)."""
    s = dict(DETECTORS)
    s["eog_invert"] = m["eog_invert"]
    s["vert_invert"] = m["vert_invert"]
    for sig, key in (("eog_h", "eog"), ("eog_v", "vert"), ("blink", "blink")):
        amp, noise = m["amplitude"][sig], m["noise"][sig]
        if not amp:
            continue
        thr = max(0.5 * amp, 2.0 * noise)
        s[f"{key}_threshold"] = round(thr, 2)
        if key in ("eog", "vert", "blink"):
            s[f"{key}_unit"] = round(amp, 2)  # size of one gesture; the zone tracker and blink-vs-look rule use these
        s[f"{key}_floor"] = round(min(max(0.25 * amp, 1.3 * noise), 0.8 * thr), 2)
    return s


def evaluate(rows: np.ndarray, labels: list[str], settings: dict, fs: float = FS) -> dict:
    """Run the real detectors with `settings` and score them against the prompts."""
    t = rows[:, 0]
    # The prompts are shuffled with no return to centre between them, so the live "opposite look is the
    # return" rule must be off here or every direction change would be scored as a miss.
    detections = [e for e in Pipeline(fs, {**settings, "look_return_hold_ms": 0}).process(rows) if isinstance(e, Detection)]
    segs = segments(t, labels)
    out = {}
    for sig, gestures in SIGNAL_GESTURES.items():
        prompts = [(g, a, b) for g, a, b in segs if g in gestures]
        if not prompts:
            continue
        hits = sum(
            any(d.gesture == g and a <= d.ts * 1000 <= b + MATCH_SLACK_US for d in detections) for g, a, b in prompts
        )
        rest_s = triggered = 0
        for label, a, b in segs:
            if label != "rest":
                continue
            a = a if a == segs[0][1] else a + REST_SKIP_US
            for c in range(a, b - 1_000_000 + 1, 1_000_000):
                rest_s += 1
                triggered += any(d.source == sig and c <= d.ts * 1000 < c + 1_000_000 for d in detections)
        acc = hits / len(prompts)
        ftr = triggered / rest_s if rest_s else 0.0
        out[sig] = {
            "accuracy": round(acc, 3),
            "false_trigger_rate": round(ftr, 3),
            "reliability": round(score(acc, ftr), 3),
            "attempts": len(prompts),
            "rest_seconds": rest_s,
        }
    return out


def calibrate(rows: np.ndarray, labels: list[str], fs: float = FS) -> dict:
    m = measure(rows, labels, fs)
    settings = thresholds(m)
    signals = evaluate(rows, labels, settings, fs)
    for sig in signals:
        signals[sig]["amplitude"] = m["amplitude"][sig] and round(m["amplitude"][sig], 1)
        signals[sig]["noise"] = round(m["noise"][sig], 1)
    return {"created": datetime.now().isoformat(timespec="seconds"), "settings": settings, "signals": signals}


def load_calibration(path: Path = CAL_PATH) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def load_csv(path: str | Path) -> tuple[np.ndarray, list[str]]:
    rows, labels = [], []
    with open(path, newline="") as f:
        r = csv.reader(f)
        next(r)
        for line in r:
            rows.append([int(x) for x in line[:4]])
            labels.append(line[4] if len(line) > 4 else "rest")
    return np.array(rows, dtype=np.int64), labels


def synthetic_session(reps: int = 10, rest_s: float = 20.0, seed: int | None = None, gain: dict | None = None):
    """The record.py protocol, generated instantly (no real-time wait) — dry runs and tests."""
    from sources.synthetic import SyntheticEXG
    from tools.record import REST_S, prompt_seconds, prompts_for

    exg = SyntheticEXG(seed=seed)
    for sig, g in (gain or {}).items():
        exg.degrade(sig, g)
    rng = np.random.default_rng(seed)
    plan = [("rest", rest_s)]
    for g in prompts_for(reps, rng):
        plan += [(g, prompt_seconds(g)), ("rest", REST_S)]
    rows, labels = [], []
    for label, secs in plan:
        if label != "rest":
            exg.trigger(label, delay_s=0.3)
        chunk = exg.chunk(int(secs * exg.fs))
        rows.append(chunk)
        labels += [label] * len(chunk)
    return np.vstack(rows), labels


def post_to_backend(result: dict, patient_id: str) -> None:
    base = BACKEND_WS_URL.replace("ws://", "http://").replace("wss://", "https://").removesuffix("/ws/signal")
    for sig, r in result["signals"].items():
        body = {"patient_id": patient_id, "signal": sig, "accuracy": r["accuracy"], "false_trigger_rate": r["false_trigger_rate"]}
        req = urllib.request.Request(f"{base}/calibration", json.dumps(body).encode(), {"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=3).read()


def report(result: dict) -> str:
    lines = [f"{'signal':8} {'accuracy':>9} {'false trig/s':>13} {'reliability':>12} {'amplitude':>10} {'noise':>7} {'n':>4}"]
    for sig, r in result["signals"].items():
        lines.append(
            f"{sig:8} {r['accuracy']:>9.0%} {r['false_trigger_rate']:>13.0%} {r['reliability']:>12.2f}"
            f" {r['amplitude'] or 0:>10.1f} {r['noise']:>7.1f} {r['attempts']:>4}"
        )
    s = result["settings"]
    lines.append(
        f"thresholds: eog {s['eog_threshold']} (floor {s['eog_floor']}, invert={s['eog_invert']}), "
        f"look up/down {s['vert_threshold']} (floor {s['vert_floor']}, invert={s['vert_invert']}), "
        f"blink {s['blink_threshold']} (floor {s['blink_floor']})"
    )
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--source", choices=["synthetic", "serial"], default="synthetic")
    p.add_argument("--port")
    p.add_argument("--file", help="calibrate from a recorded CSV instead of prompting")
    p.add_argument("--reps", type=int, default=10)
    p.add_argument("--patient", default="p1")
    p.add_argument("--no-post", action="store_true", help="don't send results to the backend")
    p.add_argument("--cue", action="store_true", help="show and speak each prompt on the /calibrate page (dot + voice)")
    args = p.parse_args()

    if args.file:
        rows, labels = load_csv(args.file)
    elif args.source == "synthetic":
        rows, labels = synthetic_session(args.reps)
    else:
        from tools.cue_server import CueServer
        from tools.record import record
        from tools.streams import open_stream

        cues = CueServer() if args.cue else None
        rows, labels = load_csv(record(open_stream("serial", args.port), args.reps, cues=cues))

    result = calibrate(rows, labels)
    print(report(result))
    CAL_PATH.write_text(json.dumps(result, indent=2))
    log = HERE / "recordings" / f"calibration-{datetime.now():%Y%m%d-%H%M%S}.json"
    log.parent.mkdir(exist_ok=True)
    log.write_text(json.dumps(result, indent=2))
    print(f"saved {CAL_PATH.name} (live thresholds) and {log.relative_to(HERE)}")
    if not args.no_post:
        try:
            post_to_backend(result, args.patient)
            print("posted to backend /calibration")
        except OSError as e:
            print(f"backend not reachable ({e}); results saved locally only")


if __name__ == "__main__":
    main()
