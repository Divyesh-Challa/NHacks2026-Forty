# Radial wheel: patient screen redesign

Status: draft for approval · 2026-11-07 · author: Lawrence (with Claude)
Replaces the split-mode patient board. Code freeze is Sun Nov 9, 7:00 AM MDT, so this is scoped as an MVP.

## Why

Split mode ("pick the half that has your phrase") only works if the person keeps watching the screen to see what is in each half. People with ALS are often lying down, tired, or have the screen out of view. Eye movement still produces an EOG signal with the eyes closed, so the interface should work without looking at anything.

The radial wheel does that: every option sits in a **fixed direction** (up, down, left, right) that the person **learns by heart**, the way signs are learned. An optional audio aid reads options aloud while they learn or when unsure. The screen becomes a helper for the people around them, not a requirement.

## Goals (MVP)

1. A patient can build and speak "I want water" with four eye directions plus a jaw clench, with no need to look at the screen.
2. Positions never move unless someone chooses to move them, so memory works.
3. When eye control fades, the existing remap still kicks in: the wheel switches to scan mode with jaw clench as select. This is still the core pitch.
4. A missing word (e.g. "video game") can be added once, by the patient spelling it or a caregiver adding it from their phone, and is then suggested in that context.
5. Works with no hardware: keyboard simulator, and a mouse "flick" simulator.

## Non-goals (MVP)

- Phrase predictions. The prediction strip comes off the patient screen for now (backend code stays); it comes back once the setup flow is decided.
- Pinning learned words to permanent slots.
- A caregiver editor for the wheel tree itself (topics, starters, items). The tree is seed data.
- LLM sentence polishing. Sentences come from fixed templates (see below); an LLM pass can be added later with the safety checks from the EyeWords plan.
- Diagonal (8-direction) wheels.
- Routing the audio aid to a separate earpiece. The browser can't pick an audio output for speech.

## Anti-goals (a failure even if it technically works)

- Anything that makes a slot's content move on its own (reordering by frequency, inserting learned words into a direction).
- Anything that depends on where the eyes are pointing (hover, dwell, cursor position). EOG only sees jumps.
- Speaking a message the person did not confirm. Audio-aid read-outs are not messages.
- Breaking the eye → jaw remap demo.

## How it works

### The wheel

Four slots in fixed directions plus a **centre**:

- **Up / Down / Left / Right**: options.
- **Centre**: the suggestion slot. It holds at most one learned word for the current path, read aloud by the aid.

Levels form a tree. The person picks a slot by looking that way. **The picked slot keeps its word and stays where it is; the other three slots are replaced** with options that follow from it.

Example, "I want water":

| Level | Up | Right | Down | Left | Look |
|---|---|---|---|---|---|
| 1 Topics | Food | Needs | Feelings | Yes / No | up → Food |
| 2 Starters | **Food** (kept) | I want | I don't want | I need | right → I want |
| 3 Groups | Drinks | **I want** (kept) | Meals | Snacks | up → Drinks |
| 4 Items | **Drinks** (kept) | Water | Juice | Spell… | right → Water |

They can finish at any level: stopping after level 2 gives "I want food", after level 3 "I want a drink".

**Capacity comes from depth.** Each level has three free directions, so a branch that needs more options splits into groups (Food › I want › Drinks › Water) rather than paging. The tree can be as deep as a branch needs; most messages should stay within four looks. **Spell…** sits in one fixed direction on every level whose options are end items.

**Yes / No is permanent** in the left slot of level 1: left → Yes / No, then up = Yes, down = No (left stays kept; right is empty). Two looks and a clench. People (family, nurse) move under Needs.

### Controls

| Action | Gesture | Command (new contract) |
|---|---|---|
| Pick a slot | look up / down / left / right | `UP` `DOWN` `LEFT` `RIGHT` |
| Go back a level | look toward the kept slot again | (no new gesture; the UI treats it as back) |
| Accept the centre suggestion | double blink | `ACCEPT` |
| Finish | jaw clench → sentence is read back; second jaw clench speaks it | `SELECT` |
| Cancel the read-back | any look | (UI) |
| HELP | jaw held 2 s | `HELP` |

At level 1 (no kept slot) looking toward a topic always picks it; there is nothing to go back to.

### Sentences (MVP: templates, no LLM)

The path is topic → starter → (groups…) → item. The sentence is `starter + ` the deepest word picked after it: the item, else the group, else the topic ("I want" + "food" → "I want food."). Each word carries the form it takes in a sentence (`Drinks` → "a drink"). Branches with no starter (Yes / No, Feelings) speak their end item directly. Each starter carries its own template in seed data (e.g. `I don't want {x}`), so negation can never be lost.

The sentence is always read back and confirmed before it is spoken (the second jaw clench). Only the confirmed sentence is sent as `spoken`.

### Audio aid

A setting on the patient screen, on by default for the demo.

- On entering a level: reads the four options, e.g. "up water, right back, down soup, left spell".
- On a centre suggestion: reads it, e.g. "suggestion: video game".
- It must sound different from real speech (quieter, faster, and a short tone first) and is never sent as `spoken` or logged as a message.

### Scan fallback (the remap)

When the input manager decides eye movement is unreliable (same rules as today: 10 readings below 60% to drop, 20 readings ≥ 75% to recover), the patient screen switches to **scan mode on the same wheel**: a highlight steps up → right → down → left → centre every 1.5 s, the aid reads each one, and the best remaining gesture (jaw clench in the stage demo) picks it. In scan mode, finishing and HELP are extra scan steps, as today.

Wheel mode needs both horizontal (`eog_h`) and vertical (`eog_v`) eye movement to be healthy. If either drops, it's scan.

### Personal words

- **Adding by spelling:** the **Spell…** slot opens the existing letter board, driven in scan mode (highlight steps through letters, jaw clench picks) whatever the current mode. Finishing reads the word back; a jaw clench confirms and saves it.
- **Adding by caregiver:** in the caregiver app, a "Words" section lets them type a word and choose where it belongs from a list of paths (e.g. "Food › I want"). It reaches the patient screen live. A per-patient setting allows or blocks caregiver additions; on by default.
- **Saved as a link** from the path to the word: `Food › I want → video game`, with a use count and last-used time, per patient, in SQLite.
- **Suggestion:** the centre shows the strongest link for the current path, scored by use count with recent use weighted more (exact decay is the builder's call). Ties go to the newest word.
- Using a suggestion (accept + speak) increments its count.

### Simulators

- **Keyboard:** arrow keys = four looks, `B` = double blink (`ACCEPT`), `Space` = jaw clench (`SELECT`), hold `H` 2 s = HELP, `M` = toggle wheel/scan. Replaces the current mapping in `frontend/src/lib/keyboardSim.ts`.
- **Mouse flick:** moving the cursor a set distance from where it rests, in one direction, sends one look event; the cursor has to return near its rest point before it can fire again, like eyes returning to centre. Clicks and hovering do nothing. Distance thresholds go in config.
- **Synthetic source:** must be able to script `look_up` / `look_down`.

## Contract changes

Lawrence approved making these on his own branch; the team agrees through the PR review (TASKS.md asks for agreement before contract changes).

These touch `CLAUDE.md`, `backend/app/models.py`, `frontend/src/lib/types.ts` and `signal/messages.py` together:

1. **Commands:** add `UP`, `DOWN`, `ACCEPT` to the five existing ones.
2. **Modes:** `split` is replaced by `wheel`. `scan` stays.
3. **Gestures:** `look_up` / `look_down` already exist in the contract but nothing emits them. The signal service must emit them from A1 and report `eog_v` reliability.
4. **Spoken event:** patient → backend `spoken` gains an optional `path` (e.g. `["Food", "I want", "water"]`) so the backend can count word use.
5. **Personal words:** `GET /patients/{id}/words`, `POST /patients/{id}/words` (caregiver, JWT), and a `words_updated` event to the patient screen.
6. **Wheel tree:** seed data replaces `DEFAULT_BOARDS` as the patient's vocabulary. Served from a `GET /patients/{id}/wheel` endpoint (or folded into boards — builder's call).

## What changes where

- **frontend:** new `RadialWheel` component (wheel + scan on the wheel), new `Patient.tsx` flow, audio aid in `lib/tts.ts`, new keyboard mapping, new mouse-flick simulator, "Words" section in `Caregiver.tsx`. `SplitBoard` is retired from the patient screen.
- **backend:** input manager gains wheel mode (needs `eog_h` + `eog_v`) and UP/DOWN/ACCEPT mappings; its tests are updated, keeping the remap, hysteresis and debounce cases. Word links table, words endpoints, `path` handling on `spoken`. `/demo` page and `scripts/demo_check.py` follow the new demo.
- **signal:** `look_up` / `look_down` detection on A1 (today the blink detector discards long vertical excursions as "a vertical look"; that's where it goes), `eog_v` reliability, calibration prompts for up/down.

## Stage demo (updated)

1. Wearer builds "I want water" with up → right → up, jaw clench, jaw clench. It's spoken.
2. Demo toggle weakens the eyes. Banner: eye movement is getting harder to read, switching to jaw clench. Wearer finishes a message in scan mode by clenching.
3. Caregiver adds "video game" under Food › I want from the phone; it appears as the centre suggestion and the wearer accepts it.
4. HELP: jaw hold → caregiver phone alarms.

## Build order (if time runs short, stop from the bottom)

1. Wheel UI + keyboard simulator on seed data, frontend only (no contract change needed to start).
2. Contract change + input manager wheel mode + scan on the wheel. Demo steps 1, 2, 4 work on synthetic data.
3. `look_up` / `look_down` on real A1 + calibration.
4. Personal words: caregiver add → centre suggestion. Demo step 3.
5. Spelling a new word from the wheel.
6. Mouse-flick simulator.

## Risks

- **Vertical EOG shares A1 with blinks.** Looking up and blinking are both positive excursions on A1; the detector separates them by duration (blink < 400 ms). Needs checking on real electrodes early (build step 3).
- **Double blink with eyes closed** may be awkward for the wearer. If so, `ACCEPT` moves to another gesture; the contract keeps it a separate command so only the mapping changes.
- **Depth:** deeper trees mean more looks per message. Keep common messages within four looks when writing the seed tree.

## Left to the builder

Visual design of the wheel, aid voice settings, the suggestion decay formula, mouse-flick distances, file and component names, whether the wheel tree has its own endpoint.

## Calls made in review (Claude's, not yet confirmed by Lawrence)

- **Yes / No sits in the left slot of level 1**, and People moves under Needs to make room.
- **Items live under the full path** (`Food › I want` and `Food › I don't want` have their own items), so an item's direction is fixed per path and can be memorized.
- **End of a branch:** picking an item that has no children leaves the wheel as is, with that item marked as picked, and waits. Jaw clench finishes; looking toward the picked item again goes back. Depth can vary by topic. A level may have fewer than three options; empty directions are blank and do nothing.
- **Read-back always plays**, whether or not the audio aid is on, in the aid's voice (tone first, quieter). It is never sent as `spoken`. Only the confirmed sentence is spoken in the main voice.
- **Scan mode finish:** a "Finish" step reads the sentence back. The scan then alternates between two steps, "Speak" and "Cancel", and SELECT picks one. The centre step in scan mode means accept the suggestion, via SELECT, so it works without blink.
- **No middle fallback in the MVP:** today, losing eye movement while blink and jaw are healthy keeps split mode (blink = LEFT, jaw = RIGHT). Under this design it goes straight to scan. A step-scan (blink steps, jaw picks) could bring that back later.

## Decided by Lawrence

- Capacity comes from depth, not paging.
- Yes / No gets a permanent spot.
- Predictions are off the patient screen for the MVP.
- Contract changes happen on his branch and are reviewed in the PR.
