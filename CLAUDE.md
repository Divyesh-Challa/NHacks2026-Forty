# Relay — project context for Claude Code

You are helping a student team build **Relay** at natHacks 2026 (Standard Division, Healthcare & Accessibility theme). This file is the source of truth for what we're building, how it's structured, and what matters most. Read it fully before writing code.

## Hard constraints

- **Deadline:** code freeze Sunday Nov 9, 2026, 7:00 AM MDT. Submission (public GitHub repo + README) due 11:00 AM MDT.
- **All code must be written during the competition.** Do not paste in code from previous projects. Using open-source libraries is fine.
- **Synthetic data only.** Never use or invent real patient data. Seed data must be obviously fake.
- **Never speak or send a message the user did not confirm.** Predictions are suggestions; only a `SELECT` command makes text-to-speech fire.
- **No secrets in the repo.** API keys go in `.env` (git-ignored). Provide `.env.example`.
- Prefer simple, working, demoable code over completeness. A feature that works live beats three half-built ones.

## What Relay is

A communication system for people with ALS that keeps working as their abilities decline. It reads several body signals (eye movement, double blinks, eyebrow raise), measures how reliably the person can control each one, and maps controls to the most reliable signals. When one signal fades (e.g., eye control weakens), Relay automatically switches to another (e.g., double blink) without changing the board the person uses.

**Differentiation (why this isn't just another eye-gaze app):**
1. **Adapts as the disease progresses** — automatic, reliability-based remapping across multiple signals. This is the core feature. Protect it above everything else.
2. **Faster** — context-aware LLM phrase prediction reduces selections per message.
3. **Camera-free and caregiver-connected** — electrodes work lying flat, in the dark, with glasses; HELP alerts reach a caregiver's phone; caregivers edit phrase boards remotely.

Competitors for reference: Tobii Dynavox (camera eye tracking, ~$5–10k), Google Look to Speak (free Android app, needs a mounted phone with a clear camera view, single input). Research EOG spellers exist but use one signal and are slow.

## The demo we're building toward (5-minute pitch)

1. A teammate wears electrodes and selects "I need water" by looking left/right; accepts a predicted phrase; Relay speaks it aloud.
2. We simulate declining eye control (a demo toggle lowers the eye channel's gain). Relay detects falling reliability, shows a banner, switches to scan mode with double blink as `SELECT`, and the teammate finishes the next message by double-blinking.
3. Teammate triggers HELP; a caregiver phone (browser) alerts with sound and notification.

Everything you build should serve this sequence working reliably on stage.

## Architecture

```
Sources (EXG pills via Arduino, synthetic generator, keyboard simulator)
        │ raw samples
        ▼
Signal service (Python process)  — filters, gesture detectors, per-signal reliability
        │ gesture events over WebSocket  (/ws/signal)
        ▼
Backend (FastAPI)
   ├─ Input manager   — gestures → 8 commands; picks wheel/scan mode; remaps on reliability
   ├─ Prediction      — LLM phrase suggestions, fixed fallback list
   ├─ Auth            — caregiver login (JWT); patient device pairs via 6-digit code
   └─ SQLite          — patients, caregivers, boards, messages, calibration
        │ commands / reliability / mode_change / alert over WebSocket
        ▼
Frontend (React)
   ├─ /patient/:id    — radial wheel (wheel + scan), spelling, read-back, TTS, audio aid
   └─ /caregiver      — login, live alerts, message history, phrase editor, reliability chart
```

### Repo layout (lives at the repo root; `relay/` below means the root)

```
relay/
  CLAUDE.md
  README.md
  .env.example
  arduino/relay_exg/relay_exg.ino       # reads A0–A2, prints CSV over serial
  signal/                               # signal service (Python)
    run.py                              # entry: pick source, stream gestures to backend
    sources/arduino_serial.py
    sources/synthetic.py                # fake EOG/blink generator (use tonight)
    filters.py
    detectors.py
    calibration.py
    reliability.py
    tests/
  backend/
    app/main.py
    app/ws.py
    app/input_manager.py
    app/predict.py
    app/auth.py
    app/db.py
    app/models.py
    app/seed.py                         # fake patient, caregiver, default boards
    tests/
  frontend/                             # Vite + React + TypeScript
    src/pages/Patient.tsx
    src/pages/Caregiver.tsx
    src/components/RadialWheel.tsx
    src/lib/wheel.ts                   # tree, navigation, sentences (tested)
    src/lib/wheelMachine.ts            # read-back, spelling, scan (tested)
    src/components/LetterBoard.tsx
    src/components/PredictionStrip.tsx
    src/components/ModeBanner.tsx
    src/lib/ws.ts
    src/lib/tts.ts
    src/lib/keyboardSim.ts
```

## Interface contract (do not change without updating this file)

The UI never sees raw signals. It only receives **eight commands** (radial wheel design: `docs/superpowers/specs/2026-11-07-radial-wheel-design.md`):

| Command | Meaning |
| --- | --- |
| `UP` / `DOWN` / `LEFT` / `RIGHT` | Pick the wheel slot in that direction (looking at the kept slot again goes back) |
| `SELECT` | Finish: read the sentence back; a second `SELECT` speaks it. In scan mode: pick the highlight |
| `ACCEPT` | Accept the centre suggestion (a learned word) |
| `BACK` | Undo / go up a level |
| `HELP` | Urgent alert to caregiver. No gesture: the patient screen has a HELP slot (Yes / No → right) that is read back and sent on `SELECT` (double blink); keyboard `H` held ~2 s is the simulator |

**Two UI modes:**
- **Wheel mode** (eye movement reliable in all four directions): four fixed slots (up/right/down/left) plus a centre suggestion. The person learns positions by heart, so it works with eyes closed; an audio aid reads options aloud. The picked slot stays put and the other three change to what follows from it.
- **Scan mode** (eye movement unreliable): the same wheel, with a highlight stepping through the slots, centre, Finish and HELP (default 1.5 s, configurable); the single best gesture = `SELECT`.

**Signal service → backend** (`/ws/signal`):
```json
{"type": "gesture", "source": "eog_h", "gesture": "look_left", "confidence": 0.88, "ts": 1762490000000}
{"type": "reliability", "signals": {"eog_h": 0.92, "eog_v": 0.85, "blink": 0.88}, "ts": 1762490000000}
```
Sources: `eog_h`, `eog_v`, `blink`, `brow`, `sim`. (Jaw clench was dropped by team decision; A2 is unused.)
Gestures: `look_left`, `look_right`, `look_up`, `look_down`, `blink_double`, `brow_raise`.

**Backend → frontend** (`/ws/patient/{id}` and `/ws/caregiver/{id}`):
```json
{"type": "command", "command": "SELECT", "via": "blink", "confidence": 0.91, "ts": 1762490000000}
{"type": "reliability", "signals": {"eog_h": 0.42, "blink": 0.95}, "mode": "scan", "mapping": {"SELECT": "blink_double"}}
{"type": "mode_change", "from": "wheel", "to": "scan", "reason": "eye movement reliability below 60%"}
{"type": "alert", "level": "urgent", "patient_id": "p1", "message": "HELP", "ts": 1762490000000}
{"type": "spoken", "patient_id": "p1", "text": "I need water", "ts": 1762490000000}
```

**Patient screen → backend** (`/ws/patient/{id}`):
```json
{"type": "spoken", "text": "I want water.", "path": ["Food", "I want", "Drinks", "Water"], "ts": 1762490000000}
{"type": "alert", "message": "HELP", "ts": 1762490000000}
{"type": "set_mode", "mode": "scan"}
```
Backend → patient also sends `{"type": "boards_updated", "boards": [...]}` after a caregiver edit.
Backend → signal service (`/ws/signal`) sends `{"type": "degrade", "signal": "eog_h", "factor": 0.3}` (demo only).

**REST:**

| Method + path | Purpose |
| --- | --- |
| `POST /auth/login` | Caregiver email + password → `{patient_id, token}`. Send `Authorization: Bearer <token>` on `PUT boards` / `GET messages`, and `?token=` on `/ws/caregiver/{id}` |
| `POST /pair` | Patient device sends 6-digit code → patient session token. The patient screen sends it as `?token=` on `/ws/patient/{id}` (currently not enforced by the backend) |
| `GET /patients/{id}/boards` | Phrase boards |
| `PUT /patients/{id}/boards` | Caregiver edits boards (broadcast update to patient WS) |
| `POST /predict` | `{patient_id, recent_messages, time_of_day, present}` → `{phrases: [..3–5]}` |
| `POST /calibration` | Store per-signal accuracy + false-trigger rate |
| `GET /patients/{id}/messages` | Message + alert history |
| `POST /demo/degrade` | Demo only: scale a signal's gain/reliability down (e.g. `{"signal": "eog_h", "factor": 0.3}`). `"signal": "eye"` degrades `eog_h` + `eog_v` together and leaves blinking alone (stage demo: eye wheel → double-blink scan in one call) |

## Component specs

### Signal service
- **Synthetic source (build first):** generates realistic-ish waveforms at 250–500 Hz: EOG horizontal steps (look left/right), vertical blink spikes, plus baseline drift and 60 Hz noise. Expose a way to script gestures (e.g. keyboard or a timed sequence) and a `degrade(signal, factor)` knob.
- **Arduino source:** `arduino/relay_exg.ino` samples A0–A2 at a fixed rate (target 500 Hz) and prints `t_us,a0,a1,a2` at 250000 baud. Channel map: A0 = horizontal EOG, A1 = vertical EOG/blinks, A2 = unused. Verify BioAmp EXG Pill output range and wiring against Upside Down Labs docs once hardware is in hand.
- **Hardware we have:** one Arduino + the BioAmp EXG Pill kit with **3 pills** (A0 horizontal EOG, A1 vertical EOG/blinks; A2 unused). **No Muse.** Every real signal comes through the EXG pills.
- **Filters:** EOG: low-pass ~10 Hz plus drift handling (use slope/derivative or high-pass ~0.1 Hz rather than absolute level).
- **Detectors:** threshold-based with refractory periods. Output `confidence` from how far past threshold the feature is.
- **Calibration:** guided prompts ("look left" ×10, "rest" 20 s, "double blink" ×10…). Compute per-signal accuracy and false-trigger rate at rest. Thresholds adapt per user from calibration.
- **Reliability (live):** `r = accuracy × (1 − false_trigger_rate)` over a rolling window. Seed from calibration; update from usage (e.g., a `BACK` right after a selection counts as a likely error).

### Input manager (the differentiator — make this solid and tested)
- Rank signals by reliability. Choose mode: wheel if horizontal and vertical eye movement (`eog_h`, `eog_v`) and a finish gesture all have `r ≥ 0.6`, else scan.
- Wheel mapping: the four looks → `LEFT/RIGHT/UP/DOWN`; first healthy of `blink_double`, `brow_raise` → `SELECT`. `ACCEPT` and `HELP` have no gesture: HELP is a slot on the wheel (Yes / No → right) that is read back and confirmed with `SELECT`; ACCEPT comes only from the keyboard/mouse simulators. No `BACK` gesture (looking at the kept slot goes back). Scan mode: best single gesture → `SELECT`.
- **Remap rule:** a mapped signal below 0.6 for its last 10 attempts triggers remap + `mode_change` event with a human-readable reason.
- **Hysteresis:** switch back only if the signal stays ≥ 0.75 for 20 attempts. No flapping.
- HELP requires hold-to-confirm. Debounce all commands (ignore duplicates within ~300 ms).
- Pure-Python logic, no I/O inside — so it's unit-testable. Write tests for: mode selection, remap on decline, hysteresis, debounce.

### Prediction
- Use the Anthropic API (`ANTHROPIC_API_KEY` in `.env`; model configurable via env, default to a fast model). Prompt for 3–5 short first-person phrases as JSON, given recent messages, time of day, and who is present.
- Timeout ~2 s; on failure or no key, return a fixed fallback list from the patient's boards.
- Send only the last few messages. Never auto-speak.

### Auth
- Time-box to ~2 hours. FastAPI + JWT (PyJWT) + `bcrypt` directly (passlib is unmaintained and breaks with bcrypt 5). Seed one caregiver (`caregiver@example.com` / documented demo password in README).
- Patient screen has **no login**: pairs once via 6-digit code, then stores its session token. (A user who can only blink can't type a password.)

### Patient frontend
- Very large targets, high contrast, readable at a distance. No time pressure in wheel mode.
- Radial wheel (seed tree in `frontend/src/lib/wheelTree.ts`): Food (I want / I don't want / I need → Drinks, Meals, Snacks → items), Needs (Body, People, Bathroom), Feelings, and Yes / No permanently on the left. Sentences come from starter templates, so "not" can't be lost; every sentence is read back and confirmed before it is spoken.
- Spell… slot adds a missing word once; it's then suggested in the centre for that path (`lib/words.ts`, browser storage until the backend words API exists).
- Phrase predictions are paused on the patient screen (backend `/predict` still works) until the setup flow is decided.
- TTS via the browser Web Speech API: the real voice only for confirmed sentences; a quieter, faster audio aid (with a tone) for read-outs and read-back.
- Keyboard simulator in `keyboardSim.ts`: arrows = UP/DOWN/LEFT/RIGHT, B = ACCEPT, Space = SELECT, Backspace = BACK, H (hold) = HELP, M = toggle wheel/scan, F = mouse-flick simulator, A = audio aid. Must work with no hardware.
- Mode banner on `mode_change`: e.g. "Eye movement is getting harder to read. Switching to double blink."

### Caregiver frontend
- Mobile-friendly. Login → live alert feed (sound + browser Notification on HELP), message history, phrase board editor (changes push live to patient), per-signal reliability chart over time.

## Build order

**Tonight (no hardware):**
1. Repo skeleton, `.env.example`, README stub.
2. Backend: FastAPI app, SQLite models, seed data, WebSocket hub, keyboard-sim path end to end.
3. Input manager + unit tests.
4. Patient frontend: radial wheel + scan + TTS, driven by keyboard sim.
5. Signal service: synthetic source, filters, detectors, reliability, tested on synthetic data; streams to backend.
6. Caregiver page with live HELP alerts. Auth (time-boxed).

**Saturday (hardware):** Arduino sketch + serial source, calibration flow, live reliability, demo degrade toggle, prediction, board editor, reliability chart. Full end-to-end run; record backup demo video.

**Priority if time runs short:** input manager + live switch > wheel/scan boards > HELP alerts > prediction > auth > board editor > reliability chart.

## How judges score (for tradeoff decisions)

Six criteria, 10 points each: technical execution (justified decisions, components integrated), prototype functionality and usability (works reliably for intended users), creativity and innovation (original reframe), impact, feasibility and continuation path, pitch and demo (claims supported by the demo). Plus a 5-point written summary.

Implications for you:
- Reliability of the live demo matters more than feature count.
- Make technical decisions explicit and visible (README section explaining filters, thresholds, reliability formula, hysteresis — with reasons).
- Log calibration accuracy numbers; we'll quote them in the pitch.

## Conventions

- Python 3.11+, FastAPI, type hints, `pytest`. Frontend: Vite + React + TypeScript, functional components, no heavy UI framework required.
- Keep config (thresholds, scan interval, reliability cutoffs) in one config file / env, not hard-coded across files.
- Small commits with clear messages; the team is working in parallel on separate folders.
- README must include: concept, architecture, how to run each part (with and without hardware), demo credentials, technical decisions, credits.
