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
- [ ] `db.py`: SQLModel tables + seed on startup (replace the in-memory store)
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
- [ ] `signal/sources/synthetic.py`: real waveforms (EOG steps, blink spikes, EMG bursts, drift, 60 Hz) + `degrade()`, so B1's detectors can be tested without hardware
- [ ] `signal/tools/plot_live.py`: live plot of raw + filtered channels from the Arduino (or a recorded CSV), for tuning thresholds and electrode placement with Nathaniel
- [ ] Record CSV sessions of real gestures (look L/R, blink, clench, rest) so detectors can be tested offline
- [ ] `reliability.py`: rolling-window `r = accuracy × (1 − false_trigger_rate)`. Send a reliability event about once per second: the input manager counts each reading as one attempt, so 10 low readings ≈ 10 s to remap on stage
- [ ] `calibration.py`: guided prompts → POST `/calibration`; **log accuracy numbers for the pitch**

**Both:** README "Technical decisions": filters, thresholds, reliability formula

## Role C: Patient frontend (owner: Tolu)
Done = demo step 1 works with the keyboard alone.
- [ ] `SplitBoard` / `ScanBoard` polish: big targets, high contrast, readable at a distance
- [ ] `LetterBoard` (spelling via the same split/scan logic)
- [ ] `PredictionStrip`: call `/predict` after each message; selecting a chip speaks it
- [ ] `ModeBanner` copy: "Eye movement is getting harder to read. Switching to jaw clench."
- [ ] Show the current mapping (which gesture does what) from `reliability` events
- [ ] Pairing flow: patient page uses the stored token

## Role D: Caregiver app + auth + prediction (owner: Fikayo)
Done = demo step 3 works on a phone browser.
- [ ] `backend/app/auth.py`: bcrypt-hashed caregiver in the DB, JWT required on caregiver routes + WS
- [ ] `backend/app/predict.py`: Anthropic API, 2 s timeout, JSON phrases, fallback list
- [ ] `Caregiver.tsx`: message history, board editor (PUT → live push to patient), reliability chart over time
- [ ] Test HELP alert sound + Notification on a phone over the LAN (`VITE_API_URL=http://<laptop-ip>:8000`)

---

## Integration checkpoints
1. **Fri night:** keyboard sim → patient board → TTS; synthetic gestures → backend → commands on the patient page. ✅ (scaffold)
2. **Sat midday:** hardware in the loop.
3. **Sat evening:** full demo run (all 3 steps) + record the backup video.
4. **Sun 7:00 AM MDT:** code freeze. 11:00 AM: submission.
