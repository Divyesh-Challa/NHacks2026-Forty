# Arduino setup and reflashing

How to flash the Relay firmware onto the Arduino Uno (with the BioAmp EXG Pills) and check that the signal service can read it. Written for macOS; Linux/Windows differences are noted.

## 1. One-time install

```bash
brew install arduino-cli                       # Linux/Windows: https://arduino.github.io/arduino-cli/
arduino-cli core update-index
arduino-cli core install arduino:avr           # the Uno's board package

cd signal
python3 -m venv .venv                          # skip if signal/.venv already exists
.venv/bin/pip install -r requirements.txt      # includes pyserial
```

Prefer the Arduino IDE? Open `arduino/relay_exg/relay_exg.ino`, pick board **Arduino Uno**, and press Upload. The rest of this doc still applies.

## 2. Wiring (two pills: eyes only)

| Pill | Arduino pin | Differential reading | Electrodes |
| --- | --- | --- | --- |
| 1 | `A0` | left electrode − upper-right electrode | left of the left eye/brow; above the right eye |
| 2 | `A1` | left electrode − lower-right electrode | left of the left eye/brow; below the right eye |

Every pill: VCC → 5V, GND → GND, OUT → its pin. Both share the left electrode and ground. The signal service reconstructs horizontal movement as `(A0 + A1) / 2` and vertical movement as `A0 - A1`; common blink artifacts are rejected from horizontal tracking by the sustained-look detector. **Run the laptop on battery while recording**: a charger adds a lot of 60 Hz noise.

There is no jaw channel in this setup. A held blink (about 2 seconds) is the HELP gesture.

## 3. Find the port

```bash
arduino-cli board list
```

Look for the row with `FQBN arduino:avr:uno`.

| OS | Typical port |
| --- | --- |
| macOS | `/dev/cu.usbmodem101` (use `cu.`, not `tty.`) |
| Linux | `/dev/ttyACM0` |
| Windows | `COM3` |

The port number changes between machines and USB ports. Below, replace `$PORT` with yours (`PORT=/dev/cu.usbmodem101`).

## 4. Flash

From the repo root:

```bash
arduino-cli compile -b arduino:avr:uno arduino/relay_exg
arduino-cli upload  -b arduino:avr:uno -p $PORT arduino/relay_exg
```

**Close anything using the port first** (`plot_live`, `run.py`, `calibration.py`, Arduino Serial Monitor), or the upload fails with "port busy". Only one program can hold the port at a time.

## 5. Check it works

From `signal/`:

```bash
PORT=$PORT .venv/bin/python - <<'PY'
import os, time, numpy as np
from tools.streams import SerialStream
s = SerialStream(os.environ["PORT"]); time.sleep(2.5); s.read(); time.sleep(3); r = s.read()
print("rows", len(r), "| rate %.1f Hz" % (1e6 / np.diff(r[:, 0]).mean()))
for i, n in enumerate(["A0", "A1"], 1):
    print(n, "mean %.0f std %.1f" % (r[:, i].mean(), r[:, i].std()))
PY
```

Expected: about 1500 rows, rate **500.0 Hz**, and A0 and A1 near **512** with a small std (a few counts) when powered pills are on a resting person.

| You see | Meaning |
| --- | --- |
| Means near 512, std 1 to 5 | Healthy resting signal |
| A0 or A1 jumping across the full 0 to 1023 range, std about 490 | Input is floating: pill not powered, OUT not connected, or wrong pin. (A2 doing this is expected, it is unconnected.) |
| Rate well under 500 Hz | Baud mismatch; see the table below |
| 0 rows | Wrong port, port busy, or board still resetting (wait 2 to 3 s after connecting) |

## 6. Use it in the app

From `signal/`, in this order (stop each before starting the next):

```bash
.venv/bin/python -m tools.plot_live --source serial --port $PORT              # raw: check electrode placement
.venv/bin/python -m tools.plot_live --source serial --port $PORT --filtered   # what the detectors see
.venv/bin/python calibration.py --source serial --port $PORT                  # guided calibration, about 3 min
.venv/bin/python run.py --source arduino --port $PORT                         # stream gestures to the backend
```

Looking left/right should move both raw channels in the same direction. Looking up/down should move A0 and A1 in opposite directions; a blink should appear similarly on both channels. Calibration derives the thresholds and polarity from these reconstructed signals.

## 7. Changing the firmware settings

The sketch and the Python side must agree:

| Change | Sketch (`arduino/relay_exg/relay_exg.ino`) | Python side |
| --- | --- | --- |
| Sample rate | `SAMPLE_RATE_HZ` | `sample_rate_hz` in `config/relay.toml` (filters read it; a mismatch silently breaks every filter) |
| Baud | `Serial.begin(...)` | `baud` defaults in `signal/tools/streams.py` and `signal/sources/arduino_serial.py` |
| Pin to signal mapping | the `analogRead(A0/A1)` lines | none, as long as output order stays shared-upper, shared-lower |

Rules of thumb:
- Keep the rate at about **500 Hz**: the detectors and calibration are tuned for it.
- Pick a baud that divides the Uno's 16 MHz clock: **250000** (current), 500000 or 1000000. 230400 is about 3.5% off and garbles lines.
- Lines are up to 26 bytes, so you need baud of at least rate × 26 × 10. At 500 Hz that is 130 kbaud, which is why 115200 is not enough.

Output format, one line per sample: `t_us,a0,a1`, where `t_us` is `micros()` at the moment of sampling (wraps every 71.6 min; resolution 4 µs on a 16 MHz Uno).

## 8. Other sketches in `arduino/`

`arduino/EOGFilter/` holds Upside Down Labs' stock examples (MIT licensed). They are **not** compatible with the app: single channel, no timestamp, 75 or 125 Hz, and `EOGFilter` high-passes at 0.5 Hz, which causes fake opposite-direction looks (see `signal/filters.py`). Use them only to eyeball A0 in the Arduino IDE Serial Plotter at 115200 baud, then reflash `relay_exg`. The Arduino IDE needs one sketch per folder, so don't open that folder directly.

## Troubleshooting

- **`upload` says port busy / not found:** close other programs using it, unplug and replug, re-run `arduino-cli board list`.
- **macOS permission prompt or no port at all:** try a different USB cable (some are charge-only).
- **Linux "permission denied":** `sudo usermod -aG dialout $USER`, then log out and in.
- **Garbled or half lines in the first second:** normal; the board resets when the port opens, and the reader skips bad lines.
