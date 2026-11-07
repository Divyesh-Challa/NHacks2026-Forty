# Relay — team tasks

Spec and contract: [CLAUDE.md](CLAUDE.md). Tunables: `config/relay.toml`.
**Branches:** `backend/<topic>`, `signal/<topic>`, `frontend/<topic>` → PR into `main`.
**Contract files:** `backend/app/models.py`, `frontend/src/lib/types.ts`, `signal/messages.py`, and the CLAUDE.md contract. Change them together and post in team chat first.

Every file that still needs work has a `SCAFFOLD STATUS` / `TODO (Role X)` header. `grep -rn "TODO (Role" .` lists them.

---

## Role A: Backend core + Input manager (owner: ___)
The core feature. Done = demo step 2 works with the synthetic source and the degrade toggle.
- [ ] `backend/app/input_manager.py`, TDD against `backend/tests/test_input_manager.py` (turn each xfail into a real test)
  - [ ] reliability ranking; split if ≥2 gestures with r ≥ 0.6, else scan
  - [ ] preferred mappings (look L/R → LEFT/RIGHT; else blink_double/jaw_clench); scan: best gesture → SELECT
  - [ ] remap after 10 attempts below 0.6 → `mode_change` with a human-readable reason
  - [ ] hysteresis: switch back only after 20 attempts ≥ 0.75
  - [ ] 300 ms debounce; HELP hold-to-confirm (2 s or 3×)
- [ ] `ws.py`: broadcast `mode_change`; HELP command → `alert` to caregiver
- [ ] `db.py`: SQLModel tables + seed on startup (replace the in-memory store)
- [ ] README "Technical decisions": remap and hysteresis rules

## Role B: Signal service + hardware (owner: ___)
Done = gestures from real electrodes reach the backend; calibration numbers recorded.
- [ ] `signal/sources/synthetic.py`: real waveforms (EOG steps, blink spikes, EMG bursts, drift, 60 Hz), `degrade()`
- [ ] `filters.py`, `detectors.py` (thresholds + refractory + confidence), `reliability.py` (rolling window), with tests on synthetic data
- [ ] Saturday: wire the Arduino + EXG pills and verify against the Upside Down Labs docs; `arduino_serial.py`
- [ ] Saturday: `muse_brainflow.py` (confirm the board ID for the dongle)
- [ ] `calibration.py`: guided prompts → POST `/calibration`; **log accuracy numbers for the pitch**
- [ ] README "Technical decisions": filters, thresholds, reliability formula

## Role C: Patient frontend (owner: ___)
Done = demo step 1 works with the keyboard alone.
- [ ] `SplitBoard` / `ScanBoard` polish: big targets, high contrast, readable at a distance
- [ ] `LetterBoard` (spelling via the same split/scan logic)
- [ ] `PredictionStrip`: call `/predict` after each message; selecting a chip speaks it
- [ ] `ModeBanner` copy: "Eye movement is getting harder to read. Switching to jaw clench."
- [ ] Show the current mapping (which gesture does what) from `reliability` events
- [ ] Pairing flow: patient page uses the stored token

## Role D: Caregiver app + auth + prediction (owner: ___)
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
