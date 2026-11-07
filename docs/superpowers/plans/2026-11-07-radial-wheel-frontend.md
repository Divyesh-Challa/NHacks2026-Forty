# Radial Wheel (frontend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the split-board patient screen with the four-direction radial wheel. It must work with the keyboard and mouse-flick simulators and fall back to scan mode on the same wheel.

**Architecture:** All behaviour lives in pure TypeScript modules under `frontend/src/lib/`:
- tree navigation and sentences: `wheel.ts`
- the phase machine (wheel, read-back, spell, scan): `wheelMachine.ts`
- learned words: `words.ts`
- the mouse-flick detector: `flickSim.ts`

They are tested with Node's built-in test runner. Node 24 strips TypeScript types itself, so no new dependency is needed. `Patient.tsx` becomes a thin shell: it feeds commands and ticks into `step()` and carries out the effects it returns (aid speech, real speech, learning, HELP). Backend and signal changes (wheel mode in the input manager, `look_up`/`look_down`, the words endpoints, the caregiver Words tab) are **out of scope** and are queued as follow-ups in Task 7.

**Tech Stack:** React 19, TypeScript, Vite, `node --test`, the Web Speech API, Web Audio.

**Spec:** `docs/superpowers/specs/2026-11-07-radial-wheel-design.md`

## Global Constraints

- Never speak a message the user did not confirm. Only a `say` effect calls `speak()` and sends `spoken`, and only a SELECT during sentence read-back produces it.
- Audio-aid output is never sent as `spoken` and never logged as a message. It plays a short tone first and is quieter and faster than real speech.
- Read-back always plays, even with the aid turned off.
- Slot positions never move on their own. Learned words appear only in the centre.
- Nothing depends on cursor or eye position. The flick simulator emits discrete look events only.
- Scan interval comes from `GET /config` → `ui.scan_interval_ms` (default 1500). HELP hold is 2000 ms.
- The patient screen must work with no backend, using the keyboard simulator alone.
- Test files are `src/lib/*.test.ts`. They import siblings with explicit `.ts` extensions and use only `import type` for types (Node type stripping).

## Review Focus

1. **The backend still speaks the old contract.** It sends mode `split` and only LEFT/RIGHT/SELECT/BACK/HELP. Every incoming `split` must read as `wheel`, and BACK must go up a level. Pinned in Task 4 (`normalizeEvent` test).
2. **A stray command during read-back or spelling.** A look during sentence read-back cancels without speaking. ACCEPT during read-back does nothing. Looks during spelling do nothing. Pinned in Task 3.
3. **Mode switching mid-message.** Going from wheel to scan keeps the half-built path and restarts the highlight at the first target. Pinned in Task 3 (`mode action keeps the path`).
4. **Broken or blocked localStorage.** Bad JSON or a throwing `localStorage` gives an empty word list, never a crash. Pinned in Task 2.
5. **Empty or whitespace spelling.** Choosing Speak with nothing spelled returns to the wheel without learning anything. Pinned in Task 3.

---

### Task 1: Wheel tree, navigation and sentences

**Files:**
- Create: `frontend/src/lib/wheel.ts`, `frontend/src/lib/wheelTree.ts`, `frontend/src/lib/wheel.test.ts`
- Modify: `frontend/package.json` (add `"test": "node --test src/lib/"`), `frontend/tsconfig.app.json` (add `"exclude": ["src/**/*.test.ts"]`), `scripts/gates.sh` (add `gate frontend-tests bash -c "cd frontend && npm test -s"` after `frontend-lint`)

**Interfaces:**
- Produces (`wheel.ts`):
  ```ts
  export type Dir = 'up' | 'right' | 'down' | 'left'
  export const DIRS: Dir[]                      // ['up','right','down','left'], clockwise; also scan order
  export interface WheelNode {
    word: string                                // shown on the slot and read by the aid
    phrase?: string                             // form inside a sentence ("a drink"); default word.toLowerCase()
    template?: string                           // starters only: "I want {x}."
    say?: string                                // full sentence for a leaf with no starter above it
    spell?: true                                // the Spell… slot
    learned?: true                              // a learned word placed in the centre
    children?: Partial<Record<Dir, WheelNode>>
  }
  export interface Pick { dir: Dir | 'centre'; node: WheelNode }
  export interface WheelView { slots: Record<Dir, WheelNode | null>; kept: Dir | null; picked: Dir | 'centre' | null }
  export function view(root: WheelNode, path: Pick[]): WheelView
  export function look(root: WheelNode, path: Pick[], dir: Dir): Pick[]
  export function back(path: Pick[]): Pick[]
  export function sentence(path: Pick[]): string | null
  export function keyChain(path: Pick[]): string[]   // owner path key, then its ancestors; words joined ' › '; never ''
  export function branch(from: Dir, nodes: (WheelNode | null)[]): Partial<Record<Dir, WheelNode>>
  export function validateTree(root: WheelNode): string[]   // [] when valid
  ```
- Produces (`wheelTree.ts`): `export const WHEEL: WheelNode` (the root; `word: ''`) and `export const SPELL: WheelNode` (`{ word: 'Spell…', spell: true }`).

**Rules the code must follow:**
- The *owner* is the last pick whose node has children. The root owns the level when there is no such pick.
- `view`:
  - Root owner: slots = root's children, `kept` = null.
  - Otherwise: slots = the owner's children plus the owner itself in its own direction, and `kept` = the owner's direction.
  - If the last pick is a leaf, `picked` = its direction, and the level shown is the owner's.
- `look`, with no leaf picked:
  - Toward `kept` → back one level.
  - Toward an empty slot → path unchanged.
  - Otherwise → push the pick.
- `look`, with a leaf picked:
  - Toward `picked` → unpick it.
  - Toward `kept` → pop the leaf and the owner.
  - Toward another filled slot → replace the leaf with that pick.
- `back` pops one pick (a leaf counts as one).
- `sentence`:
  - Find the last node with a `template`, at index *i*.
  - If none: return the last node's `say`, or null.
  - Otherwise, `x` is the last node when it comes after *i*, else the node at *i−1*, else there is none and the result is null.
  - Return the template with `{x}` replaced by `x.phrase ?? x.word.toLowerCase()`.
  - Spell nodes never appear in a path.
- `branch(from, nodes)` assigns `nodes` in order to the directions in `DIRS` other than `from`. A `null` leaves that direction empty.
- `validateTree`: a child may not sit in its parent's own direction. The root is exempt. Each error string names the path.

**Tree content (`wheelTree.ts`).** Use `branch()` everywhere below the root, so directions follow the rule automatically.
- Root (explicit directions):
  - up `Food`
  - right `Needs`
  - down `Feelings`
  - left `Yes / No`
- `Food` → `I want` (`I want {x}.`), `I don't want` (`I don't want {x}.`), `I need` (`I need {x}.`)
- Every starter → `Drinks` (phrase `a drink`), `Meals` (`a meal`), `Snacks` (`a snack`)
- Groups:
  - `Drinks` → `Water` (`water`), `Juice` (`juice`), `SPELL`
  - `Meals` → `Soup` (`soup`), `Toast` (`toast`), `SPELL`
  - `Snacks` → `Fruit` (`fruit`), `Crackers` (`crackers`), `SPELL`
- `Needs` → `Body`, `People`, `Bathroom` (say `I need the bathroom.`)
  - `Body` → `Reposition me` (say `Please reposition me.`), `I'm in pain` (say `I'm in pain.`), `Temperature`
    - `Temperature` → `Too hot` (say `I'm too hot.`), `Too cold` (say `I'm too cold.`)
  - `People` → `Family` (say `Please call my family.`), `Nurse` (say `Please call the nurse.`)
- `Feelings` → `Happy` (say `I'm happy.`), `Tired` (say `I'm tired.`), `More`
  - `More` → `Frustrated` (say `I'm frustrated.`), `Thank you` (say `Thank you.`), `Love you` (say `I love you.`)
- `Yes / No` → `branch('left', [Yes (say 'Yes.'), null, No (say 'No.')])`, so Yes is up, right is empty and No is down.

- [ ] **Step 1: Write the failing tests** in `wheel.test.ts` (`node:test` + `node:assert/strict`), using a helper `go(...dirs: Dir[])` that folds `look(WHEEL, path, d)` from `[]`:
  - `validateTree(WHEEL)` deep-equals `[]`
  - `view(WHEEL, [])` slots: up `Food`, right `Needs`, down `Feelings`, left `Yes / No`; `kept` null
  - `view(WHEEL, go('up'))`: up `Food`, `kept` 'up', right `I want`, down `I don't want`, left `I need`
  - `view(WHEEL, go('up','right','up'))`: `kept` 'up', right `Water`, down `Juice`, left `Spell…`
  - `go('up','up')` deep-equals `[]` (looking at the kept slot goes back)
  - `go('up','right','up','right')`: `view(...).picked` is 'right'. Looking right again gives a path of length 3. Looking down instead puts `Juice` last.
  - `go('left','right')` has length 1 (empty slot is a no-op)
  - `sentence(go('up','right'))` → `'I want food.'`
  - `sentence(go('up','right','up'))` → `'I want a drink.'`
  - `sentence(go('up','right','up','right'))` → `'I want water.'`
  - `sentence(go('up','down','right','up'))` → `"I don't want soup."` (from `I don't want`, down is the kept slot, so Meals sits right)
  - `sentence(go('left','up'))` → `'Yes.'`; `sentence(go('left','down'))` → `'No.'`
  - `sentence(go('up'))` → null; `sentence([])` → null
  - `keyChain(go('up','right','up'))` deep-equals `['Food › I want › Drinks', 'Food › I want', 'Food']`; `keyChain([])` deep-equals `[]`
  - A hand-built tree with a child in its parent's direction makes `validateTree` return one error

- [ ] **Step 2: Run** `cd frontend && npm test`. Expected: FAIL (module not found).
- [ ] **Step 3: Implement** `wheel.ts` and `wheelTree.ts` per the Interfaces and Rules above. Add the `test` script, the tsconfig `exclude` and the gates line.
- [ ] **Step 4: Run** `cd frontend && npm test && npm run build`. Expected: all tests pass and the build succeeds.
- [ ] **Step 5: Commit** `git commit -m "Wheel tree, navigation and sentence templates"`

---

### Task 2: Learned words store

**Files:**
- Create: `frontend/src/lib/words.ts`, `frontend/src/lib/words.test.ts`

**Interfaces:**
- Produces:
  ```ts
  export interface WordLink { key: string; word: string; count: number; last: number }  // last = ms epoch
  export const HALF_LIFE_DAYS = 7
  export function learn(links: WordLink[], key: string, word: string, now: number): WordLink[]
  export function suggest(links: WordLink[], keys: string[], now: number): string | null
  export function loadWords(patientId: string): WordLink[]          // localStorage 'relay_words_<id>'
  export function saveWords(patientId: string, links: WordLink[]): void
  ```
- `learn`:
  - Trims the word. An empty word returns `links` unchanged.
  - A word already under that key (matched ignoring case) gets `count + 1` and `last = now`.
  - Otherwise a new link is added with `count: 1`.
  - Never mutates the input.
- `suggest`:
  - Walks `keys` in order. The first key that has any links wins.
  - Within it, the highest `count * 0.5 ** (ageDays / HALF_LIFE_DAYS)` wins. Ties go to the larger `last`.
  - Returns null when no key has links.
- `loadWords` and `saveWords` wrap every `localStorage` access in try/catch. Bad JSON, or JSON that isn't an array, loads as `[]`.

- [ ] **Step 1: Write the failing tests:**
  - `learn([], 'Food › I want', ' video game ', 1)` → one link `{key:'Food › I want', word:'video game', count:1, last:1}`
  - Learning `'Video Game'` again under the same key at `now=2` → one link, count 2, last 2
  - `learn(links, k, '   ', 3)` returns the same array (`assert.equal`)
  - `suggest` with links under `'Food › I want'` and keys `['Food › I want › Drinks','Food › I want','Food']` returns that word (ancestor fallback)
  - A word with count 4 last used 21 days ago (score 0.5) loses to count 1 used now
  - `suggest([], ['x'], 0)` → null
  - With `globalThis.localStorage` stubbed to return `'not json'`, `loadWords('p1')` deep-equals `[]`. With it stubbed to throw, `loadWords('p1')` deep-equals `[]` and `saveWords('p1', [])` does not throw.
- [ ] **Step 2: Run** `npm test`. Expected: FAIL.
- [ ] **Step 3: Implement** `words.ts`.
- [ ] **Step 4: Run** `npm test`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "Learned words: links, decayed suggestion, local storage"`

---

### Task 3: Wheel machine (phases, read-back, spelling, scan)

**Files:**
- Create: `frontend/src/lib/wheelMachine.ts`, `frontend/src/lib/wheelMachine.test.ts`
- Modify: `frontend/src/lib/types.ts`. Only the `Command` union changes in this task: it gains `'UP' | 'DOWN' | 'ACCEPT'`.

**Interfaces:**
- Consumes: `view`, `look`, `back`, `sentence`, `keyChain`, `Pick`, `WheelNode`, `Dir`, `DIRS` (Task 1); `SPELL_ITEMS`, `SPELL_SPEAK`, `SPELL_DELETE`, `SPELL_SPACE` from `lib/spell.ts`.
- Produces:
  ```ts
  export type Phase = 'wheel' | 'readback' | 'spell'
  export interface Readback { kind: 'sentence' | 'word'; text: string }
  export interface MachineState { phase: Phase; path: Pick[]; readback: Readback | null; spelled: string; scanIndex: number }
  export const INITIAL: MachineState                     // wheel, [], null, '', 0
  export type Action = { type: 'command'; command: Command } | { type: 'tick' } | { type: 'mode' }
  export interface Ctx { root: WheelNode; mode: 'wheel' | 'scan'; suggestFor: (path: Pick[]) => string | null }
  export type Effect =
    | { kind: 'aid'; text: string; always?: true }      // always = read-back, plays even with the aid off
    | { kind: 'say'; text: string; path: string[] }      // the ONLY thing that speaks
    | { kind: 'learn'; key: string; word: string }
    | { kind: 'help' }
  export type Target = Dir | 'centre' | 'finish' | 'help' | 'speak' | 'cancel'
  export function targets(s: MachineState, ctx: Ctx): (Target | string)[]   // string = a SPELL_ITEMS entry in the spell phase
  export function step(s: MachineState, a: Action, ctx: Ctx): [MachineState, Effect[]]
  export function announce(v: WheelView, suggestion: string | null): string  // "up Food, right back, down Soup, left Spell…, centre video game"
  ```

**Behaviour.** Commands are honoured in both modes. Scan adds `tick` and `SELECT`-on-target.

| Phase | Input | Result |
|---|---|---|
| any | `HELP` | `[s, [help]]`, state unchanged |
| wheel | `UP/DOWN/LEFT/RIGHT` | If the slot is `SPELL`: phase `spell`, `spelled ''`, `scanIndex 0`, aid `'Spell a word'`. Else path = `look(...)`; aid = `announce` of the new view, or the picked leaf's word when a leaf was just picked |
| wheel | `ACCEPT` | If `suggestFor(path)` gives a word: drop any leaf pick, push `{dir:'centre', node:{word, phrase: word, learned: true}}`, aid the word. Else nothing |
| wheel | `SELECT` | `sentence(path)` is null: aid `'Pick a few words first'`. Else phase `readback` `{kind:'sentence'}`, aid `{text, always: true}` |
| wheel | `BACK` | `path = back(path)`, aid `announce` |
| readback | `SELECT` | Sentence: `say {text, path: words}`, plus `learn` for a `learned` leaf (key = `keyChain(path)[0]`); then `INITIAL`. Word: `learn {key: keyChain(path)[0], word}`, push it as the centre pick, phase `wheel`, aid the word |
| readback | any look, `BACK` | Cancel: a sentence goes back to phase `wheel` with the path kept; a word goes back to `spell` with `spelled` kept. Aid `'Cancelled'`. No `say` |
| readback | `ACCEPT` | Nothing |
| spell | `SELECT` | Item at `scanIndex`. `SPELL_SPEAK`: trimmed `spelled` empty → phase `wheel`, else `readback {kind:'word'}` with aid always. `SPELL_DELETE` drops the last character, `SPELL_SPACE` appends a space, any other item appends that letter. Then `scanIndex 0` |
| spell | `BACK` | Phase `wheel`, `spelled ''` |
| spell | looks, `ACCEPT` | Nothing |
| spell | `tick` | `scanIndex + 1` (wraps), aid the item text without its leading symbol |
| wheel/readback, scan mode | `tick` | `scanIndex + 1` over `targets()` (wraps), aid the target's label |
| wheel/readback, scan mode | `SELECT` | Act on `targets()[scanIndex]`: a direction → as that look; `centre` → as `ACCEPT`; `finish` → as wheel `SELECT`; `help` → help; `speak` → as readback `SELECT`; `cancel` → as cancel. Reset `scanIndex 0` |
| any | `tick` in wheel mode outside spell | Nothing |
| any | `mode` | `scanIndex 0`, path kept, aid `announce` |

`targets`:
- Spell phase: `SPELL_ITEMS`.
- Readback phase: `['speak', 'cancel']`.
- Wheel phase: the filled directions in `DIRS` order, then `'centre'` if `suggestFor(path)`, then `'finish'` if `sentence(path)` isn't null, then `'help'`.

In wheel mode, SELECT in the wheel phase always means finish. It never acts on a scan target.

- [ ] **Step 1: Write the failing tests.** Use helpers `run(actions, ctx)` (folds `step`, collects effects) and `cmd(c)`. Base ctx is `{root: WHEEL, mode: 'wheel', suggestFor: () => null}`.
  - UP, RIGHT, UP, RIGHT, SELECT → phase `readback` and no `say` yet. One more SELECT → exactly one `say` `{text:'I want water.', path:['Food','I want','Drinks','Water']}`, and the state equals `INITIAL`.
  - SELECT on `INITIAL` → no `readback` and no `say`
  - In sentence read-back, LEFT → phase `wheel`, path length 4, no `say`. ACCEPT in read-back → state unchanged.
  - No `say` effect appears anywhere in a run of every command except the final readback SELECT (assert across the first test's effects)
  - The read-back aid effect has `always: true`
  - Spelling: UP, RIGHT, UP, LEFT → phase `spell`. Ticks to reach `'V'` (index found with `SPELL_ITEMS.indexOf`), SELECT; same for `'I'`. Tick to index 0 (`SPELL_SPEAK`), SELECT → readback `{kind:'word', text:'VI'}`. SELECT → effect `learn {key:'Food › I want › Drinks', word:'VI'}`, phase `wheel`, last pick `dir 'centre'`.
  - Spell with nothing spelled, then Speak → phase `wheel`, no `learn`
  - LEFT/UP during spell → state unchanged
  - With `suggestFor: () => 'video game'`: UP, RIGHT, ACCEPT, SELECT, SELECT → `say 'I want video game.'` and `learn {key:'Food › I want', word:'video game'}`
  - Scan mode: `targets(INITIAL, scanCtx)` deep-equals `['up','right','down','left','help']`. A tick, then SELECT → path's first pick is `Needs`. In sentence read-back, targets deep-equal `['speak','cancel']`.
  - Mode action keeps the path: after UP, RIGHT, `{type:'mode'}` with the scan ctx → path length 2, `scanIndex` 0
  - HELP in each phase → one `help` effect and an identical state
- [ ] **Step 2: Run** `npm test`. Expected: FAIL.
- [ ] **Step 3: Implement** `wheelMachine.ts` and add the three commands to `Command` in `types.ts`.
- [ ] **Step 4: Run** `npm test && npm run build`. Expected: PASS. The build may fail in `Patient.tsx` or `Demo.tsx` only because of the new commands. If so, leave it for Task 6 and note it in the commit.
- [ ] **Step 5: Commit** `git commit -m "Wheel machine: read-back, spelling, scan targets, effects"`

---

### Task 4: Contract types, keyboard simulator, mouse flick

**Files:**
- Modify: `frontend/src/lib/types.ts`, `frontend/src/lib/ws.ts`, `frontend/src/lib/keyboardSim.ts`, `frontend/src/lib/api.ts` (the `getConfig` type), `config/relay.toml` (`[ui]`), `frontend/src/pages/Demo.tsx` (mode labels)
- Create: `frontend/src/lib/flickSim.ts`, `frontend/src/lib/flickSim.test.ts`, `frontend/src/lib/normalize.test.ts`

**Interfaces:**
- `types.ts`:
  - `Mode = 'wheel' | 'scan'`
  - `PatientEvent` spoken gains `path?: string[]`
  - `set_mode` mode becomes `'split' | 'scan'`, with a comment that the backend still calls wheel mode "split" until the backend follow-up lands
- `ws.ts`: `export function normalizeEvent(ev: any): ServerEvent` maps `mode`, `from` and `to` values of `'split'` to `'wheel'`. `connect` applies it to every incoming event before calling the handler, so Patient, Caregiver and Demo all get it.
- `keyboardSim.ts`:
  - Signature: `attachKeyboardSim(onCommand: (c: Command) => void, toggles: { mode(): void; flick(): void; aid(): void }): () => void`
  - Keys: ←/→/↑/↓ = LEFT/RIGHT/UP/DOWN, `B` = ACCEPT, Space = SELECT, Backspace = BACK, hold `H` 2 s = HELP, `M` = mode, `F` = flick, `A` = aid
  - Update the header comment
- `flickSim.ts`:
  - `export class FlickDetector { constructor(opts: { flickPx: number; rearmPx: number }); move(dx: number, dy: number): Dir | null }`
  - `dx`/`dy` are measured from the viewport centre, with screen y pointing down
  - It starts disarmed. Coming within `rearmPx` of the centre arms it.
  - While armed, going beyond `flickPx` emits the dominant-axis direction and disarms
- `relay.toml` `[ui]`: `flick_px = 160` and `flick_rearm_px = 50`, each with a comment. The backend already serves all of `[ui]` from `/config`, so no backend change is needed.
- `getConfig` type: `ui` gains `flick_px: number; flick_rearm_px: number`

- [ ] **Step 1: Write the failing tests:**
  - `flickSim.test.ts`, with `new FlickDetector({flickPx:160, rearmPx:50})`:
    - `move(200,0)` → null (not armed yet)
    - `move(0,0)` → null
    - `move(200,0)` → 'right'
    - `move(250,0)` → null
    - `move(10,10)` → null
    - `move(0,-200)` → 'up'
    - after re-arming, `move(150,170)` → 'down'
    - after re-arming, `move(-170,20)` → 'left'
  - `normalize.test.ts`:
    - `normalizeEvent({type:'mode_change', from:'split', to:'scan', reason:'r'})` → `from 'wheel'`
    - `normalizeEvent({type:'reliability', signals:{}, mode:'split', mapping:{}}).mode` → 'wheel'
    - a `command` event comes back unchanged
- [ ] **Step 2: Run** `npm test`. Expected: FAIL.
- [ ] **Step 3: Implement** the files above.
  - Demo shows `Wheel mode` with the line `four eye directions pick a slot` instead of the split wording.
  - `normalizeEvent` must not import browser globals at module top level: `ws.ts` is imported by the test. If it does, move `normalizeEvent` into `lib/normalize.ts`.
- [ ] **Step 4: Run** `npm test`. Expected: PASS. (The build is checked in Task 6.)
- [ ] **Step 5: Commit** `git commit -m "Contract: UP/DOWN/ACCEPT and wheel mode; four-way keyboard sim; mouse flick detector"`

---

### Task 5: Audio aid and the wheel component

**Files:**
- Modify: `frontend/src/lib/tts.ts`, `frontend/src/components/LetterBoard.tsx`, `frontend/src/index.css`
- Create: `frontend/src/components/RadialWheel.tsx`

**Interfaces:**
- `tts.ts`:
  - Keep `speak(text)` as it is: it is the real voice and still cancels everything.
  - Add `export function aid(text: string): void`. It plays an 880 Hz, 80 ms tone through Web Audio, then speaks with `volume 0.5` and `rate 1.3`. It cancels a previous *aid* utterance only, not a `speak` in progress: track the last aid utterance and skip if `speechSynthesis.speaking` comes from a real `speak`. Wrap the Web Audio part in try/catch.
- `RadialWheel.tsx`:
  ```ts
  export function RadialWheel(props: {
    view: WheelView; suggestion: string | null
    highlight: Target | null          // scan target, null in wheel mode
    extras: Target[]                  // 'finish' / 'help' in scan mode, shown as a row under the wheel
  }): JSX.Element
  ```
  - A 3×3 grid: up top-centre, left mid-left, centre middle, right mid-right, down bottom-centre.
  - The kept slot shows its word plus a small "back" label, in the accent outline.
  - The picked slot is filled with the accent colour.
  - An empty slot is blank and dimmed.
  - The centre shows the suggestion, or nothing.
  - The highlighted target gets the existing `.item.active` look and the `scan-timer` bar.
  - Each slot shows an arrow glyph (↑ → ↓ ←) so people watching learn the directions.
- `LetterBoard.tsx`: add `export function LetterGrid({ items, active }: { items: string[]; active: number })`, using the existing `.scan` grid and `.item.active` classes.
- `index.css`: add `.wheel` grid styles in the existing token style: big type, at least 120 px slots, high contrast. Remove the `.half*` / `.split` rules.

- [ ] **Step 1: Implement** the files above. There is no unit test: this is presentational, and the logic behind it is tested in Tasks 1–3.
- [ ] **Step 2: Run** `npm run lint`. Expected: no new warnings in these files.
- [ ] **Step 3: Commit** `git commit -m "Radial wheel component, letter grid, audio aid voice"`

---

### Task 6: Patient screen on the wheel

**Files:**
- Modify: `frontend/src/pages/Patient.tsx` (rewrite)
- Delete: `frontend/src/components/SplitBoard.tsx`, `frontend/src/components/ScanBoard.tsx`. `PredictionStrip.tsx` stays in the repo, unused; predictions come back later.

**Interfaces:**
- Consumes: everything from Tasks 1–5.

**Wiring (`Patient.tsx`):**
- State:
  - `machine` (a `MachineState`, mirrored in a ref so the socket and timers see the latest)
  - `mode` (`Mode`, starts `'wheel'`)
  - `links` (from `loadWords(id)`)
  - `aidOn` and `flickOn`, saved in localStorage as `relay_aid` and `relay_flick` behind try/catch; aid defaults on
  - `spoken`, `helpActive`, `connected`, `modeChange`, `mapping`, `scanMs`
- `ctx = { root: WHEEL, mode, suggestFor: (p) => suggest(links, keyChain(p), Date.now()) }`
- `run(action)`: call `step(ref.current, action, ctx)`, set the state, then carry out each effect:
  - `aid`: call `aid(text)` when `aidOn || always`
  - `say`: `speak(text)`, prepend to `spoken`, and send `{type:'spoken', text, path, ts}`
  - `learn`: `learn(...)`, then `saveWords`
  - `help`: the existing `help()`, which sends the `alert`
- Socket `command` events → `run({type:'command', command})`
- `reliability` / `mode_change` set `mode` (already normalized by `ws.ts`); a mode change also calls `run({type:'mode'})`
- `boards_updated` is ignored
- A tick interval of `scanMs` runs `run({type:'tick'})` while `mode === 'scan' || machine.phase === 'spell'`
- Keyboard sim toggles:
  - `mode`: same as today, but sends `set_mode` `'split'`/`'scan'` when connected; offline it flips locally and shows a banner
  - `flick` and `aid` flip their settings
- While `flickOn`, a `pointermove` listener feeds `FlickDetector.move(clientX - innerWidth/2, clientY - innerHeight/2)` and runs the matching look command. Thresholds come from `getConfig().ui`, falling back to 160/50.
- Render:
  - Header: path breadcrumb (`Home › Food › I want`), mode, `aid on/off`, `flick on/off`, `online/offline`, and controls built from `mapping`. Add `look_up` / `look_down` to `GESTURE_LABELS`.
  - `ModeBanner`
  - Spell phase: `LetterBoard` (`spelled`) + `LetterGrid`
  - Other phases: `RadialWheel` (with `highlight` = `targets()[scanIndex]` in scan mode, `extras` in scan mode)
  - In read-back, an overlay with the text plus "Clench to speak · look to cancel" (wheel mode), or the speak/cancel targets (scan mode)
  - Footer `Said: “…”` and the HELP overlay, as today

- [ ] **Step 1: Implement** the rewrite and delete the two components.
- [ ] **Step 2: Run** `npm test && npm run build && npm run lint`. Expected: tests pass, the build succeeds, and lint has no new warnings.
- [ ] **Step 3: Check it live.** Run `scripts/screenshot.sh /tmp/wheel /patient/p1` and look at the PNG: the root wheel shows Food, Needs, Feelings, Yes / No. Then `make frontend` with no backend and, in the browser, use the keyboard:
  - ↑ → ↑ → Space Space speaks "I want water."
  - `M` then Space on the first highlight picks Food in scan mode
  - ↑ → ↑ ← opens spelling
  - holding H shows the HELP overlay
  - `F` and a mouse flick up from the centre picks Food

  Write down anything that didn't behave.
- [ ] **Step 4: Run** `scripts/gates.sh quick`. Expected: every gate passes. If demo-check depends on split boards, list it for Task 7 rather than editing the backend.
- [ ] **Step 5: Commit** `git commit -m "Patient screen: radial wheel, read-back, spelling, scan fallback, flick sim"`

---

### Task 7: Contract docs and follow-up queue

**Files:**
- Modify: `CLAUDE.md`, `TASKS.md`, `README.md` (patient-screen and keyboard sections only)

- [ ] **Step 1: Update `CLAUDE.md`:**
  - The command table gains UP, DOWN, ACCEPT.
  - "Two UI modes" becomes wheel and scan, as in the spec.
  - Add `path` on `spoken`.
  - Update the keyboard simulator line and the Patient frontend section (wheel, aid, Yes / No, spelling; predictions paused).
  - Note that the backend still sends `split`, and the frontend reads it as `wheel` until the backend follow-up lands.
- [ ] **Step 2: Add to the `TASKS.md` loop queue**, in order:
  1. `backend-engineer`: input manager wheel mode. It needs `eog_h` + `eog_v`. Map `look_up/down` → UP/DOWN, `blink_double` → ACCEPT, `jaw_clench` → SELECT. Rename `split` to `wheel`. Update the tests, keeping the remap, hysteresis and debounce cases. Update `demo_check.py`.
  2. `signal-engineer`: `look_up` / `look_down` from A1 (the long vertical excursions `BlinkDetector` drops today), `eog_v` reliability, and calibration prompts for up and down.
  3. `backend-engineer`: a `word_links` table, `GET/POST /patients/{id}/words`, `words_updated`, and counting `path` on `spoken`. `frontend-engineer`: move `words.ts` from localStorage to that API, and add a caregiver Words tab.
  4. Bring predictions back, after the setup flow is decided.
- [ ] **Step 3: Update the README** keyboard keys and patient-screen description.
- [ ] **Step 4: Commit** `git commit -m "Docs: wheel contract, keyboard keys, follow-up tasks"`
