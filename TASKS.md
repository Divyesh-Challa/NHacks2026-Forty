# Relay — team tasks

Spec and contract: [CLAUDE.md](CLAUDE.md). Tunables: `config/relay.toml`.
**Branches:** `backend/<topic>`, `signal/<topic>`, `frontend/<topic>` → PR into `main`.
**Contract files:** `backend/app/models.py`, `frontend/src/lib/types.ts`, `signal/messages.py`, and the CLAUDE.md contract. Change them together and post in team chat first.

Tolu and Fikayo: C and D are interchangeable. Swap if you prefer.

Every file that still needs work has a `SCAFFOLD STATUS` / `TODO (Role X)` header. `grep -rn "TODO (Role" .` lists them.

---

## Role A: Backend core + Input manager (owner: Divyesh)
The core feature. Done = demo step 2 works with the synthetic source and the degrade toggle.
- [x] `backend/app/input_manager.py`, TDD against `backend/tests/test_input_manager.py` (20 tests)
  - [x] split/scan selection; preferred mappings; scan picks the most reliable gesture
  - [x] remap after 10 readings below 0.6 → `mode_change` with a human-readable reason
  - [x] hysteresis: switch back only after 20 readings ≥ 0.75
  - [x] 300 ms per-command debounce; HELP = `jaw_hold` (hold-to-confirm lives in the detector)
- [x] `ws.py`: broadcast `mode_change`; HELP command → `alert` to caregiver
- [x] `db.py`: SQLModel tables + seed on startup
- [x] `/demo/degrade` accepts `"eye"` (eog_h + blink) for the one-call stage demo
- [x] `/demo` presenter page: degrade/restore buttons + live reliability, mode and mapping
- [ ] README "Technical decisions": remap and hysteresis rules

## Role B: Signal service + hardware (owners: Nathaniel + Lawrence)
Done = gestures from real electrodes reach the backend; calibration numbers recorded.
Both of you produce the same output: dicts from `signal/messages.py`, yielded by a source's `events()`.

**B1: Nathaniel: EXG pills, Arduino, EOG/EMG pipeline**
- [ ] Wire the BioAmp EXG Pills and verify the output range and wiring against the Upside Down Labs docs
- [ ] `arduino/relay_exg/relay_exg.ino`: confirm a steady 500 Hz (raise the baud if lines drop)
- [ ] `signal/sources/arduino_serial.py`: parse `t_us,a0,a1,a2`
- [ ] `filters.py` (EOG low-pass + drift, EMG bandpass + notch + RMS) and `detectors.py` (thresholds, refractory period, confidence), with tests
- [ ] **HELP contract:** emit `jaw_hold` only once a clench has lasted ≥ `help_hold_ms` (2 s), and do NOT also emit `jaw_clench` for that same hold. The input manager treats `jaw_hold` as a confirmed HELP.

**B2: Lawrence: synthetic data, signal tooling, reliability, calibration**
- [x] `signal/sources/synthetic.py`: Arduino-format waveforms (EOG steps, blink spikes, EMG bursts, drift, 60 Hz, crosstalk) with ground-truth labels + `degrade()`; live stream uses a simulated detector until `detectors.py` exists
- [x] `signal/tools/plot_live.py`: live plot from synthetic / Arduino serial / CSV replay (add filtered traces once `filters.py` lands)
- [x] `signal/tools/record.py`: prompted, labelled CSV sessions
- [ ] Record real sessions with the electrodes: `python -m tools.record --source serial --port … --reps 10`
- [x] `reliability.py`: `ReliabilityTracker`, rolling windows (8 attempts, 20 rest seconds), seeded from calibration, usage errors count as misses
- [ ] **Open question (with Nathaniel):** on real hardware nobody knows when a gesture was *attempted* but missed. Proposal: outside calibration, score each signal from detected-gesture amplitude vs its calibrated amplitude, plus rest-time false triggers
- [ ] `calibration.py`: guided prompts → POST `/calibration`; **log accuracy numbers for the pitch**

**Both:** README "Technical decisions": filters, thresholds, reliability formula

## Role C: Patient frontend (owner: Tolu)
Done = demo step 1 works with the keyboard alone.
- [x] `SplitBoard` / `ScanBoard` visual polish: gesture hint on each half, dense grid for big boards (Spell), solid scan highlight + timer bar, red HELP
- [x] `LetterBoard`: "Spell" board with frequency-ordered letters, Space/Delete/Speak
- [x] `PredictionStrip`: `/predict` after each message; predictions are the first items on the home board (★), one selection to speak
- [x] `ModeBanner` shows the backend's plain-language reason
- [x] Header shows the current mapping (which gesture does what)
- [ ] Pairing flow: patient page uses the stored token

## Role D: Caregiver app + auth + prediction (owner: Fikayo)
Done = demo step 3 works on a phone browser.
- [x] bcrypt-hashed caregiver in the DB; `/auth/login` and `/pair` check the DB (done with Role A's DB work)
- [x] `backend/app/auth.py`: JWT required on caregiver routes (`PUT boards`, `GET messages`) + caregiver WS (`?token=`), scoped to the caregiver's patient
- [x] `backend/app/predict.py`: Anthropic API, 2 s timeout, JSON phrases, fallback list (needs `ANTHROPIC_API_KEY` in `.env` to use the model)
- [x] `Caregiver.tsx`: Live / History / Boards / Signals tabs; HELP banner + 3-tone sound + Notification; board editor (PUT → live push); reliability chart with the 60% line
- [ ] Test HELP alert sound + Notification on a real phone: `make frontend-https`, open the Network URL on the phone (see README "Caregiver phone")

---

## Integration checkpoints
1. **Fri night:** keyboard sim → patient board → TTS; synthetic gestures → backend → commands on the patient page. ✅ (scaffold)
2. **Sat midday:** hardware in the loop.
3. **Sat evening:** full demo run (all 3 steps) + record the backup video.
4. **Sun 7:00 AM MDT:** code freeze. 11:00 AM: submission.
