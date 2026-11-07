# Relay

A communication system for people with ALS that keeps working as their abilities decline. Relay reads several body signals (eye movement, blinks, jaw clench, eyebrow raise), measures how reliably the person can control each one, and maps the controls to the most reliable signals. When one signal fades, Relay switches to another automatically, and the board the person uses stays the same.

Built at natHacks 2026 (Healthcare & Accessibility). All data is synthetic.

## Architecture

```
Sources (EXG pills via Arduino, synthetic generator)
   │ raw samples
signal/   filters → gesture detectors → per-signal reliability
   │ gesture + reliability events   (WS /ws/signal)
backend/  input manager (gestures → LEFT/RIGHT/SELECT/BACK/HELP, split/scan, remap) · prediction · auth · SQLite
   │ command / reliability / mode_change / alert / spoken   (WS /ws/patient/{id}, /ws/caregiver/{id})
frontend/ /patient/:id (split + scan boards, TTS) · /caregiver (alerts, history, editor, chart)
```

The full interface contract is in [CLAUDE.md](CLAUDE.md). All tunables live in [`config/relay.toml`](config/relay.toml).

## Running it

Requirements: Python 3.11+ and Node 20+.

```bash
cp .env.example .env      # add ANTHROPIC_API_KEY for prediction (optional)
make setup                # venvs + npm install
make backend              # http://localhost:8000  (terminal 1)
make frontend             # http://localhost:5173  (terminal 2)
make signal               # synthetic gestures     (terminal 3, optional)
make test
make demo-check         # plays the 3 stage-demo steps end to end; run before the pitch
```

**Synthetic signals:** `make signal` streams scripted gestures. With `--script none`, it waits for you to type `l`/`r`/`b`/`j`/`h` + Enter in its terminal. `cd signal && .venv/bin/python -m tools.plot_live` shows the raw channels live; press `d` to degrade the eyes. `python -m tools.record` records labelled CSVs.

**Without hardware:** open `http://localhost:5173/patient/p1` and use the keyboard: ←/→ = LEFT/RIGHT, Space = SELECT, Backspace = BACK, hold H for 2 s = HELP, M = toggle split/scan. The patient page also works with the backend offline.

**With hardware:** flash `arduino/relay_exg/relay_exg.ino`, then `cd signal && .venv/bin/python run.py --source arduino --port /dev/tty.usbmodemXXXX`. *(TODO: Role B)*

**Caregiver phone (demo step 3):** put the phone on the same Wi-Fi as the laptop and run `make frontend-https`. Open the **Network** URL it prints, e.g. `https://192.168.x.x:5173/caregiver`, accept the self-signed certificate warning once, then log in. The login tap unlocks the alert sound; tap "enable notifications" if it's offered. HELP then sounds, vibrates (Android) and shows a notification.
- Plain `make frontend` also works on the phone, since every request goes through the dev server's `/api` proxy, but phone browsers block notifications without HTTPS. You still get the sound, vibration and the red banner.
- iPhone Safari only shows web notifications for sites added to the Home Screen. Rely on the sound and banner there.

**Demo controls:** open `http://localhost:5173/demo` on a second laptop or phone (not the projector). It has buttons for "Degrade eyes → jaw scan", "Degrade eye movement only" and "Restore all", plus live reliability bars, the current mode and mapping, and recent switches.

**Demo degrade from the terminal (stage step 2):** this degrades both eye signals, so Relay switches from eye-movement split mode to jaw-clench scan mode after about 10 s:

```bash
curl -X POST localhost:8000/demo/degrade -H 'Content-Type: application/json' -d '{"signal":"eye","factor":0.3}'
# restore: same call with "factor": 1.0.  Single signals also work: "eog_h", "blink", "jaw"
```

The database is `backend/relay.db`, created and seeded with fake data on first start. Delete it to reset.

## Demo credentials

- Caregiver: `caregiver@example.com` / `relay-demo` (or whatever `DEMO_CAREGIVER_PASSWORD` is set to in `.env`)
- Patient pairing code: `123456`

## Technical decisions

### Input manager (`backend/app/input_manager.py`)

- **Health per signal, not per reading.** Every reliability reading for a signal counts as one attempt. A healthy signal becomes unhealthy only after **10 consecutive readings below 0.6**. One bad second never takes away a control the person is using.
- **Hysteresis.** An unhealthy signal is trusted again only after **20 consecutive readings ≥ 0.75**. The gap between 0.6 and 0.75 plus the longer recovery window keeps a signal hovering near the cutoff from flipping the board back and forth (tested in `test_no_flapping_around_cutoff`).
- **Mode choice.** Split mode uses the first healthy pair from: look left/right → blink + jaw clench → eyebrow + jaw clench. With no healthy pair, scan mode uses the most reliable healthy gesture as SELECT.
- **Announcements.** A `mode_change` with a plain-language reason (e.g. "Eye movement reliability fell below 60%. Switching to double blink and jaw clench.") goes out only when the mode or a primary control changes. Losing an optional extra like BACK changes nothing on screen.
- **HELP** is a sustained jaw clench (`jaw_hold`, ~2 s), confirmed in the detector, so an ordinary clench can never raise a false alarm. In scan mode HELP is also a scan item.
- **Debounce.** A repeated command within 300 ms is dropped, per command.
- The logic is pure Python with no I/O, so it's covered by unit tests.

### Reliability (`signal/reliability.py`)

- `r = accuracy × (1 − false_trigger_rate)`. Accuracy is measured over the last **8 gesture attempts** per signal, and the false-trigger rate over the last **20 seconds of rest**. Both windows start filled from calibration, so a new session begins at the calibrated value and real use takes over.
- The synthetic source runs a simulated detector: about 97% of gestures are detected at full strength, about 25% after `degrade(…, 0.3)`, and weaker signals false-trigger more at rest. Reliability on stage therefore falls because gestures are actually being missed.
- Measured live, with the synthetic source at its default rate: "Degrade eyes" → jaw-clench scan mode in **~19 s**, and restore → eye control in **~23 s** (recovery is intentionally stricter).

*(TODO: filters, detector thresholds, and calibration accuracy numbers.)*

## Credits

*(TODO: team, libraries: FastAPI, React, Vite, NumPy/SciPy, Upside Down Labs BioAmp EXG Pill, Anthropic API.)*
