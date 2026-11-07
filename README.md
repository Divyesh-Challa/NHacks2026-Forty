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
```

**Without hardware:** open `http://localhost:5173/patient/p1` and use the keyboard: ←/→ = LEFT/RIGHT, Space = SELECT, Backspace = BACK, hold H for 2 s = HELP, M = toggle split/scan. The patient page also works with the backend offline.

**With hardware:** flash `arduino/relay_exg/relay_exg.ino`, then `cd signal && .venv/bin/python run.py --source arduino --port /dev/tty.usbmodemXXXX`. *(TODO: Role B)*

**Demo degrade:** `curl -X POST localhost:8000/demo/degrade -H 'Content-Type: application/json' -d '{"signal":"eog_h","factor":0.3}'`

## Demo credentials

- Caregiver: `caregiver@example.com` / `relay-demo` (or whatever `DEMO_CAREGIVER_PASSWORD` is set to in `.env`)
- Patient pairing code: `123456`

## Technical decisions

*(TODO: filters, detector thresholds, reliability formula `r = accuracy × (1 − false_trigger_rate)`, remap and hysteresis rules, and the reasons for each, plus calibration accuracy numbers.)*

## Credits

*(TODO: team, libraries: FastAPI, React, Vite, NumPy/SciPy, Upside Down Labs BioAmp EXG Pill, Anthropic API.)*
