"""Guided calibration: prompts → per-user thresholds + per-signal accuracy and false-trigger rate.

  python calibration.py --source serial --port /dev/tty.usbmodem1101    # with electrodes (~3 min)
  python calibration.py --file recordings/session-….csv                 # offline, from tools.record
  python calibration.py --source synthetic                              # instant dry run

Protocol (tools/record.py): 20 s rest, then shuffled looks and double blinks,
each in a fixed window followed by 2 s rest.

From the recording:
  1. amplitude/polarity per direction = first sustained movement, before the return to centre
  2. noise per signal = typical peak in initial quiet rest chunks after settling
  3. threshold = max(50% of amplitude, 2× noise); floor (near-miss) = max(25% of amplitude, 1.3× noise)
  4. run the real Pipeline with those settings over the whole recording:
       accuracy = prompts with exactly one correct command and no other commands / prompts
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

from config import BACKEND_WS_URL, DETECTOR_OVERRIDES, DETECTORS
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
SETTLE_US = 8_000_000  # fresh electrodes swing rail to rail for several seconds (AC-coupled pill settling); not noise


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


def first_movement(d: np.ndarray, noise: float, fs: float) -> float | None:
    """Measure the first sustained departure, never a larger opposite return later in the cue."""
    gate = max(8.0, 4.0 * noise)
    width = max(1, int(0.04 * fs))
    for i in range(len(d) - width + 1):
        sign = np.sign(d[i])
        if sign and np.all(d[i:i + width] * sign > gate):
            stop = min(len(d), i + int(0.7 * fs))
            pulse = d[i:stop] * sign
            # Stop at the first return across baseline, before measuring the peak.
            ends = np.flatnonzero(pulse <= 0)
            if len(ends):
                pulse = pulse[:ends[0]]
            return float(sign * np.max(pulse))
    return None


def rest_noise(x: np.ndarray) -> float:
    """Robust background scale in ADC counts; sparse blink/contact spikes are not background.

    1.4826 converts median absolute deviation to a Gaussian standard-deviation estimate. Transient
    peaks are reported separately and still count as false commands in the full live evaluation.
    """
    return float(1.4826 * np.median(np.abs(x - np.median(x))))


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
            noise = float(np.median(np.abs(h[p] - np.median(h[p]))))
            peak = first_movement(d, noise, fs)
            if peak is not None:
                eog[label].append(peak)
        elif label in vert and p.stop > p.start:
            d = v[w] - np.median(v[p])
            noise = float(np.median(np.abs(v[p] - np.median(v[p]))))
            peak = first_movement(d, noise, fs)
            if peak is not None:
                vert[label].append(peak)
        elif label == "blink_double" and p.stop > p.start:
            blink.append(float(np.max(v[w] - np.median(v[p]))))

    rest_h, rest_v, rest_va = [], [], []
    background_h, background_v = [], []
    for label, a, b in segs:
        if label != "rest":
            continue
        # Noise comes from the initial quiet rest, not eye-return / blink recovery tails.
        if a != segs[0][1]:
            continue
        a = a + SETTLE_US if a == segs[0][1] else a + REST_SKIP_US
        for c in range(a, b - 1_000_000 + 1, 1_000_000):
            w = _window(t, c, c + 1_000_000)
            rest_h.append(float(np.max(np.abs(h[w] - np.median(h[w])))))
            rest_v.append(float(np.max(v[w] - np.median(v[w]))))
            rest_va.append(float(np.max(np.abs(v[w] - np.median(v[w])))))
            background_h.append(rest_noise(h[w]))
            background_v.append(rest_noise(v[w]))

    def polarity(samples: dict, negative: str, positive: str) -> tuple[bool, float]:
        votes = [x < 0 for x in samples[negative]] + [x > 0 for x in samples[positive]]
        agreement = max(sum(votes), len(votes) - sum(votes)) / len(votes) if votes else 0.0
        return bool(votes) and sum(votes) < len(votes) / 2, agreement

    invert, h_agreement = polarity(eog, "look_left", "look_right")
    eog_amps = [abs(x) for x in eog["look_left"] + eog["look_right"]]
    ups = vert["look_up"]
    vert_invert, v_agreement = polarity(vert, "look_down", "look_up")
    vert_amps = [abs(x) for x in vert["look_down"] + ups]
    pct = lambda xs, q: float(np.percentile(xs, q)) if xs else 0.0  # noqa: E731
    return {
        "eog_invert": invert,
        "vert_invert": vert_invert,
        "polarity_agreement": {"eog_h": h_agreement, "eog_v": v_agreement},
        "direction_amplitudes": {g: float(np.median(np.abs(xs))) for g, xs in {**eog, **vert}.items() if xs},
        "direction_counts": {g: len(xs) for g, xs in {**eog, **vert}.items()},
        "amplitude": {
            "eog_h": float(np.median(eog_amps)) if eog_amps else None,
            "eog_v": float(np.median(vert_amps)) if vert_amps else None,
            "blink": float(np.median(blink)) if blink else None,
        },
        "rest_seconds_measured": len(background_h),
        "noise": {"eog_h": pct(background_h, 50), "eog_v": pct(background_v, 50), "blink": pct(background_v, 50)},
        "rest_transient_peak": {"eog_h": pct(rest_h, 90), "eog_v": pct(rest_va, 50), "blink": pct(rest_v, 50)},
    }


def rail_warnings(rows: np.ndarray, limit: float = 0.01) -> list[str]:
    """A channel pinned at the ADC rails is a contact/saturation problem, not a threshold problem."""
    out = []
    for i, name in ((1, "A0 (horizontal)"), (2, "A1 (vertical/blink)")):
        x = rows[:, i]
        frac = float(np.mean((x <= 8) | (x >= 1015)))
        if frac > limit:
            out.append(f"WARNING: {name} hit the ADC limit {frac:.0%} of the time. Check that electrode's contact (skin prep, gel, lead strain) and recalibrate; thresholds from this run are not trustworthy.")
    return out


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
    s.update(DETECTOR_OVERRIDES)  # pinned in relay.toml [detector_overrides]; survive every recalibration
    for gesture, amp in m.get("direction_amplitudes", {}).items():
        sig = "eog_h" if gesture in ("look_left", "look_right") else "eog_v"
        prefix = "eog" if sig == "eog_h" else "vert"
        noise = m["noise"][sig]
        thr = DETECTOR_OVERRIDES.get(f"{prefix}_threshold", max(0.5 * amp, 2.0 * noise))
        s[f"{gesture}_threshold"] = round(thr, 2)
        s[f"{gesture}_floor"] = round(DETECTOR_OVERRIDES.get(f"{prefix}_floor", min(max(.25 * amp, 1.3 * noise), .8 * thr)), 2)
        s[f"{gesture}_unit"] = round(amp, 2)
    return s


def evaluate(rows: np.ndarray, labels: list[str], settings: dict, fs: float = FS) -> dict:
    """Run the real detectors with `settings` and score them against the prompts."""
    t = rows[:, 0]
    pipe = Pipeline(fs, settings)
    detections = []
    chunk = max(1, int(fs * .02))
    for i in range(0, len(rows), chunk):
        detections.extend(e for e in pipe.process(rows[i:i + chunk]) if isinstance(e, Detection))
    segs = segments(t, labels)
    out = {}
    for sig, gestures in SIGNAL_GESTURES.items():
        prompts = [(g, a, b) for g, a, b in segs if g in gestures]
        if not prompts:
            continue
        outcomes = [[d.gesture for d in detections if a <= d.ts * 1000 <= b + MATCH_SLACK_US] for g, a, b in prompts]
        hits = sum(got == [g] for (g, _, _), got in zip(prompts, outcomes))
        rest_s = triggered = 0
        for label, a, b in segs:
            if label != "rest":
                continue
            a = a + SETTLE_US if a == segs[0][1] else a + REST_SKIP_US
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
            "hits": sum(g in got for (g, _, _), got in zip(prompts, outcomes)),
            "misses": sum(g not in got for (g, _, _), got in zip(prompts, outcomes)),
            "extra_commands": sum(len(got) - int(g in got) for (g, _, _), got in zip(prompts, outcomes)),
            "directions": {g: {"exact": sum(got == [g] for (wanted, _, _), got in zip(prompts, outcomes) if wanted == g),
                                "attempts": sum(wanted == g for wanted, _, _ in prompts)} for g in gestures},
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
    warnings = rail_warnings(rows)
    if m["rest_seconds_measured"] < 5:
        warnings.append("WARNING: fewer than five seconds of initial rest remain after settling. Record a longer initial rest before calibrating.")
    for sig, gestures in (("eog_h", ["look_left", "look_right"]), ("eog_v", ["look_up", "look_down"])):
        present = any(g in labels for g in gestures)
        if present and (m["polarity_agreement"][sig] < .8 or any(m["direction_counts"][g] < 2 for g in gestures)):
            counts = ', '.join(f"{g}={m['direction_counts'][g]}" for g in gestures)
            warnings.append(f"WARNING: {sig} polarity needs at least 80% agreement and two usable movements per direction; got {m['polarity_agreement'][sig]:.0%} agreement, {counts}. Repeat calibration with clear looks and returns.")
        for g in gestures:
            amp = m["direction_amplitudes"].get(g)
            if amp and 2 * m["noise"][sig] >= amp:
                warnings.append(f"WARNING: {g} is not separated from rest noise (amplitude {amp:.1f}, noise {m['noise'][sig]:.1f}). Improve contact and keep still during the initial rest; do not lower the threshold to compensate.")
    return {"created": datetime.now().isoformat(timespec="seconds"), "settings": settings, "signals": signals,
            "measurement": m, "warnings": warnings, "valid": not warnings}


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
    rows = np.vstack(rows)
    # The hardware is AC-coupled: held looks decay and returning to centre produces the opposite
    # pulse. Include that in calibration's dry run so its live position tracker can observe returns.
    from scipy.signal import lfilter
    alpha = .5 / (.5 + 1 / exg.fs)
    rows[:, 1] = np.rint(512 + lfilter([alpha, -alpha], [1, -alpha], rows[:, 1] - rows[0, 1]))
    return rows, labels


def post_to_backend(result: dict, patient_id: str) -> None:
    base = BACKEND_WS_URL.replace("ws://", "http://").replace("wss://", "https://").removesuffix("/ws/signal")
    for sig, r in result["signals"].items():
        body = {"patient_id": patient_id, "signal": sig, "accuracy": r["accuracy"], "false_trigger_rate": r["false_trigger_rate"]}
        req = urllib.request.Request(f"{base}/calibration", json.dumps(body).encode(), {"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=3).read()


def report(result: dict) -> str:
    lines = [f"{'signal':8} {'exact acc':>9} {'rest false %':>13} {'reliability':>12} {'amplitude':>10} {'noise':>7} {'n':>4}"]
    for sig, r in result["signals"].items():
        lines.append(
            f"{sig:8} {r['accuracy']:>9.0%} {r['false_trigger_rate']:>13.0%} {r['reliability']:>12.2f}"
            f" {r['amplitude'] or 0:>10.1f} {r['noise']:>7.1f} {r['attempts']:>4}"
        )
        for gesture, counts in r.get("directions", {}).items():
            lines.append(f"  {gesture}: exactly one correct command {counts['exact']}/{counts['attempts']}")
        lines.append(f"  missed prompts: {r.get('misses', 0)}, extra commands: {r.get('extra_commands', 0)}")
    s = result["settings"]
    lines.append(
        f"thresholds: eog {s['eog_threshold']} (floor {s['eog_floor']}, invert={s['eog_invert']}), "
        f"look up/down {s['vert_threshold']} (floor {s['vert_floor']}, invert={s['vert_invert']}), "
        f"blink {s['blink_threshold']} (floor {s['blink_floor']})"
    )
    for g in ("look_left", "look_right", "look_up", "look_down"):
        if f"{g}_threshold" in s:
            lines.append(f"  {g}: threshold {s[g + '_threshold']}, floor {s[g + '_floor']}")
    transient = result.get("measurement", {}).get("rest_transient_peak")
    if transient:
        lines.append(f"Rest transient peaks (not background noise): horizontal {transient['eog_h']:.1f}, vertical {transient['eog_v']:.1f}. Extras and rest false triggers still include their effects.")
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
    for w in result["warnings"]:
        print(w)
    log = HERE / "recordings" / f"calibration-{datetime.now():%Y%m%d-%H%M%S}.json"
    log.parent.mkdir(exist_ok=True)
    log.write_text(json.dumps(result, indent=2))
    if not result["valid"]:
        print(f"Saved rejected candidate to {log.relative_to(HERE)}; existing calibration.json was preserved.")
        return
    if CAL_PATH.exists():
        (HERE / "calibration.prev.json").write_bytes(CAL_PATH.read_bytes())
    CAL_PATH.write_text(json.dumps(result, indent=2))
    print(f"saved {CAL_PATH.name} (live thresholds) and {log.relative_to(HERE)}; previous calibration backed up automatically")
    if not args.no_post:
        try:
            post_to_backend(result, args.patient)
            print("posted to backend /calibration")
        except OSError as e:
            print(f"backend not reachable ({e}); results saved locally only")


if __name__ == "__main__":
    main()
