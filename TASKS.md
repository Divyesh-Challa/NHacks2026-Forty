# Relay — team tasks

Spec and contract: [CLAUDE.md](CLAUDE.md). Tunables: `config/relay.toml`.
**Branches:** `backend/<topic>`, `signal/<topic>`, `frontend/<topic>` → PR into `main`.
**Contract files:** `backend/app/models.py`, `frontend/src/lib/types.ts`, `signal/messages.py`, and the CLAUDE.md contract. Change them together and post in team chat first.

Tolu and Fikayo: C and D are interchangeable. Swap if you prefer.

Every file that still needs work has a `SCAFFOLD STATUS` / `TODO (Role X)` header. `grep -rn "TODO (Role" .` lists them.

---

## Loop queue (agent loop: `/loop /orchestrate`)
The orchestrator takes the first unchecked item that isn't tagged `[you]` or `[hw]`, gives it to the named specialist, and opens a PR for a human to merge. Add items here, most important first. Write each one so a newcomer could prove it's done.

- [x] `frontend-engineer` Fix the oxlint warning `react(set-state-in-effect)` at `frontend/src/pages/Patient.tsx:78` without changing behaviour. Proof: `npm run lint` shows no warnings; the keyboard flow (←/→/Space, M to toggle mode) still works in a headless check
- [x] `verifier` Property test for the input manager: seeded random reliability sequences (500+) never break its invariants. Split mode always maps LEFT and RIGHT; scan mode always maps SELECT; `mode_change` only when the mode or a primary control changes; values hovering between 0.6 and 0.75 never flip the mapping; HELP is `jaw_hold` whenever jaw is healthy. Proof: the new test passes, and fails when the hysteresis check in `_all_last` is deliberately broken
- [ ] `backend-engineer` Scan-mode SELECT must not flip while values hover between the cutoffs. Today `_choose` re-picks SELECT by live reliability, so it flips when every signal is unhealthy (falls back to all of `SCAN_SELECT`) or when two scan candidates are healthy (e.g. blink + brow). Impact (reviewer): in random runs ~48% of all mode_change events were these scan→scan SELECT hops, each re-showing the ModeBanner; on stage this happens if jaw also drops below 60% after the eye degrade. Fix: keep the current SELECT while it is still healthy, or while nothing is healthy; only re-pick when it becomes unhealthy or a healthier-by-rule candidate appears through a health change. Proof: the strict xfails `test_hover_all_unhealthy_scan_keeps_select` and `test_hover_two_healthy_scan_candidates_keeps_select` in `backend/tests/test_input_manager_properties.py` now pass (remove their xfail marks and the `scan_select_is_ambiguous` skip); the existing input manager tests and demo-check still pass
- [x] `backend-engineer` Radial wheel, backend side (spec: `docs/superpowers/specs/2026-11-07-radial-wheel-design.md`; frontend already on `frontend/radial-wheel`). Input manager: rename mode `split` → `wheel`; wheel mode needs `eog_h` + `eog_v` healthy; map `look_up/look_down/look_left/look_right` → UP/DOWN/LEFT/RIGHT, `blink_double` → ACCEPT, `jaw_clench` → SELECT, `jaw_hold` → HELP; scan mode unchanged. Update `models.py` (Command + Mode), the tests (keep the remap, hysteresis, debounce and property cases) and `scripts/demo_check.py`; then drop the split→wheel mapping in `frontend/src/lib/normalize.ts`. Proof: gates pass; `/demo` shows "Wheel mode"
- [ ] `signal-engineer` Emit `look_up` / `look_down` from A1 (the long vertical excursions `BlinkDetector` drops today as "a vertical look"), report `eog_v` reliability, add up/down to calibration prompts and the synthetic source. Proof: tests on synthetic data; on real electrodes `make plot` shows up/down crossing the threshold
- [ ] `[you]` `backend-engineer` + `frontend-engineer` Learned words on the server: `word_links` table, `GET/POST /patients/{id}/words` (POST needs the caregiver JWT), `words_updated` to the patient, count `path` on `spoken`. Frontend: `lib/words.ts` uses the API instead of localStorage; caregiver "Words" tab (type a word, pick its path, per-patient allow toggle). Contract change: approve the shapes first
- [ ] `[you]` Bring phrase predictions back to the patient screen once the setup flow is decided
- [ ] `frontend-engineer` Pairing: the patient page reads the token `/pair` stored (`relay_patient_token`), sends it as `?token=` on `/ws/patient/{id}`, and shows "Paired" or "Not paired · open /pair" in the header. It must keep working with no token, since the stage demo doesn't pair. Proof: screenshots of both states; gates pass
- [ ] `docs` Stage runbook `docs/RUNBOOK.md`: which laptop and phone run what, every command in order, the `/demo` page, the caregiver phone setup, and fallbacks (electrodes fail → synthetic + keyboard; backend crash → restart; no venue Wi-Fi → phone hotspot). Proof: every command was run or checked against the Makefile
- [ ] `[you]` `backend-engineer` + `signal-engineer` Usage errors lower reliability (CLAUDE.md: a BACK right after a selection counts as a likely error). Needs a new backend → signal message, which is a **contract change**: approve the message shape first
- [ ] `[hw]` Everything under Role B that says "real electrodes"

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
- [x] README "Technical decisions": remap and hysteresis rules

## Role B: Signal service + hardware (owners: Nathaniel + Lawrence)
Done = gestures from real electrodes reach the backend; calibration numbers recorded.
Both of you produce the same output: dicts from `signal/messages.py`, yielded by a source's `events()`.

**B1: Nathaniel: EXG pills, Arduino, EOG/EMG pipeline**
- [ ] Wire the BioAmp EXG Pills and verify the output range and wiring against the Upside Down Labs docs
- [ ] `arduino/relay_exg/relay_exg.ino`: confirm a steady 500 Hz (raise the baud if lines drop)
- [x] `signal/sources/arduino_serial.py`: parse `t_us,a0,a1,a2` → `sources/pipeline.py` (filters → detectors → reliability). Needs a test on the real board: `make signal-hw PORT=…`
- [x] `filters.py` (EOG low-pass + adaptive baseline, EMG bandpass + notch + RMS) and `detectors.py` (thresholds, near-miss floor, refractory period, confidence), with tests on synthetic data
- [ ] On the real electrodes: `make plot PORT=…`. Check that each gesture clears the solid threshold line and rest stays inside the dashed floor lines. Tune `[detectors]` in `config/relay.toml` if calibration can't fix it
- [x] **HELP contract:** emit `jaw_hold` only once a clench has lasted ≥ `help_hold_ms` (2 s), and do NOT also emit `jaw_clench` for that same hold (tested)

**B2: Lawrence: synthetic data, signal tooling, reliability, calibration**
- [x] `signal/sources/synthetic.py`: Arduino-format waveforms (EOG steps, blink spikes, EMG bursts, drift, 60 Hz, crosstalk) with ground-truth labels + `degrade()`; live stream uses a simulated detector until `detectors.py` exists
- [x] `signal/tools/plot_live.py`: live plot from synthetic / Arduino serial / CSV replay (add filtered traces once `filters.py` lands)
- [x] `signal/tools/record.py`: prompted, labelled CSV sessions
- [ ] Record real sessions with the electrodes: `python -m tools.record --source serial --port … --reps 10`
- [x] `reliability.py`: `ReliabilityTracker`, rolling windows (8 attempts, 20 rest seconds), seeded from calibration, usage errors count as misses
- [x] **Live reliability on hardware:** a *near-miss* (past the floor, short of threshold) counts as a failed attempt; FTR stays at its calibrated value. Revisit after seeing real data
- [x] `calibration.py`: guided prompts → per-person thresholds, accuracy, FTR → `signal/calibration.json` + POST `/calibration`
- [ ] Run `make calibrate PORT=…` on the demo wearer and **paste the accuracy table into the README** for the pitch

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
