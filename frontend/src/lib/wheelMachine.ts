// The patient screen's state machine: wheel → read-back → speak, spelling, and scan on the wheel.
// Pure: step() returns the next state plus effects for Patient.tsx to carry out. Tests: wheelMachine.test.ts.
//
// Safety rule (CLAUDE.md): the only `say` effect comes from SELECT while a sentence is read back.
import { SPELL_DELETE, SPELL_ITEMS, SPELL_SPACE, SPELL_SPEAK } from './spell.ts'
import type { Command } from './types.ts'
import { back, DIRS, keyChain, look, sentence, view } from './wheel.ts'
import type { Dir, Pick, WheelNode, WheelView } from './wheel.ts'

export type Phase = 'wheel' | 'readback' | 'spell'
export interface Readback {
  kind: 'sentence' | 'word'
  text: string
}
export interface MachineState {
  phase: Phase
  path: Pick[]
  readback: Readback | null
  spelled: string
  scanIndex: number
}
export const INITIAL: MachineState = { phase: 'wheel', path: [], readback: null, spelled: '', scanIndex: 0 }

export type Action = { type: 'command'; command: Command } | { type: 'tick' } | { type: 'mode' }
export interface Ctx {
  root: WheelNode
  mode: 'wheel' | 'scan'
  suggestFor: (path: Pick[]) => string | null
}
export type Effect =
  | { kind: 'aid'; text: string; always?: true } // always = read-back, plays even with the aid off
  | { kind: 'say'; text: string; path: string[] } // the ONLY thing that speaks
  | { kind: 'learn'; key: string; word: string }
  | { kind: 'help' }
export type Target = Dir | 'centre' | 'finish' | 'help' | 'speak' | 'cancel'
type Result = [MachineState, Effect[]]

// Read-back targets are ['speak', 'cancel']; scanning starts on Cancel so one stray SELECT can't speak.
const READBACK_START = 1
const LOOKS: Partial<Record<Command, Dir>> = { UP: 'up', RIGHT: 'right', DOWN: 'down', LEFT: 'left' }
const aid = (text: string): Effect => ({ kind: 'aid', text })

export function announce(v: WheelView, suggestion: string | null): string {
  const parts = DIRS.filter((d) => v.slots[d]).map((d) => `${d} ${d === v.kept ? 'back' : v.slots[d]!.word}`)
  if (suggestion) parts.push(`centre ${suggestion}`)
  return parts.join(', ')
}

export function targets(s: MachineState, ctx: Ctx): (Target | string)[] {
  if (s.phase === 'spell') return SPELL_ITEMS
  if (s.phase === 'readback') return ['speak', 'cancel']
  const v = view(ctx.root, s.path)
  const out: Target[] = DIRS.filter((d) => v.slots[d])
  if (ctx.suggestFor(s.path)) out.push('centre')
  if (sentence(s.path)) out.push('finish')
  out.push('help')
  return out
}

function label(t: Target | string, s: MachineState, ctx: Ctx): string {
  if (s.phase === 'spell') return t.replace(/^[^\p{L}]+/u, '')
  const v = view(ctx.root, s.path)
  if ((DIRS as string[]).includes(t)) return t === v.kept ? 'back' : v.slots[t as Dir]!.word
  if (t === 'centre') return `suggestion ${ctx.suggestFor(s.path)}`
  return t
}

const announceAt = (path: Pick[], ctx: Ctx) => aid(announce(view(ctx.root, path), ctx.suggestFor(path)))

function lookAt(s: MachineState, dir: Dir, ctx: Ctx): Result {
  const v = view(ctx.root, s.path)
  const slot = v.slots[dir]
  if (slot?.spell && dir !== v.kept && dir !== v.picked) {
    return [{ ...s, phase: 'spell', spelled: '', scanIndex: 0 }, [aid('Spell a word')]]
  }
  const path = look(ctx.root, s.path, dir)
  if (path === s.path) return [s, []]
  const pickedLeaf = view(ctx.root, path).picked !== null && path.at(-1) !== s.path.at(-1)
  return [{ ...s, path, scanIndex: 0 }, [pickedLeaf ? aid(path.at(-1)!.node.word) : announceAt(path, ctx)]]
}

function accept(s: MachineState, ctx: Ctx): Result {
  const word = ctx.suggestFor(s.path)
  if (!word) return [s, []]
  return [{ ...s, path: withCentre(s.path, word, ctx), scanIndex: 0 }, [aid(word)]]
}

function withCentre(path: Pick[], word: string, ctx: Ctx): Pick[] {
  const base = view(ctx.root, path).picked !== null ? path.slice(0, -1) : path
  return [...base, { dir: 'centre', node: { word, phrase: word, learned: true } }]
}

function finish(s: MachineState): Result {
  const text = sentence(s.path)
  if (!text) return [s, [aid('Pick a few words first')]]
  return [{ ...s, phase: 'readback', readback: { kind: 'sentence', text }, scanIndex: READBACK_START }, [{ kind: 'aid', text, always: true }]]
}

function confirm(s: MachineState, ctx: Ctx): Result {
  const rb = s.readback!
  const key = keyChain(s.path)[0] ?? ''
  if (rb.kind === 'sentence') {
    const fx: Effect[] = [{ kind: 'say', text: rb.text, path: s.path.map((p) => p.node.word) }]
    const last = s.path.at(-1)?.node
    if (last?.learned) fx.push({ kind: 'learn', key, word: last.word })
    return [INITIAL, fx]
  }
  const path = withCentre(s.path, rb.text, ctx)
  return [
    { ...s, phase: 'wheel', path, readback: null, spelled: '', scanIndex: 0 },
    [{ kind: 'learn', key, word: rb.text }, aid(rb.text)],
  ]
}

function cancel(s: MachineState): Result {
  const phase = s.readback?.kind === 'word' ? 'spell' : 'wheel'
  return [{ ...s, phase, readback: null, scanIndex: 0 }, [aid('Cancelled')]]
}

function spellCommand(s: MachineState, c: Command, ctx: Ctx): Result {
  if (c === 'BACK') return [{ ...s, phase: 'wheel', spelled: '', scanIndex: 0 }, [announceAt(s.path, ctx)]]
  if (c !== 'SELECT') return [s, []]
  const item = SPELL_ITEMS[s.scanIndex]
  if (item === SPELL_SPEAK) {
    const word = s.spelled.trim()
    if (!word) return [{ ...s, phase: 'wheel', spelled: '', scanIndex: 0 }, [announceAt(s.path, ctx)]]
    return [
      { ...s, phase: 'readback', readback: { kind: 'word', text: word }, scanIndex: READBACK_START },
      [{ kind: 'aid', text: `${word}?`, always: true }],
    ]
  }
  const spelled = item === SPELL_DELETE ? s.spelled.slice(0, -1) : s.spelled + (item === SPELL_SPACE ? ' ' : item)
  return [{ ...s, spelled, scanIndex: 0 }, []]
}

// Scan mode: SELECT acts on the highlighted target.
function pickTarget(s: MachineState, ctx: Ctx): Result {
  const t = targets(s, ctx)[s.scanIndex]
  if (t === 'centre') return accept(s, ctx)
  if (t === 'finish') return finish(s)
  if (t === 'help') return [s, [{ kind: 'help' }]]
  if (t === 'speak') return confirm(s, ctx)
  if (t === 'cancel') return cancel(s)
  if ((DIRS as string[]).includes(t)) return lookAt(s, t as Dir, ctx)
  return [s, []]
}

export function step(s: MachineState, a: Action, ctx: Ctx): Result {
  if (a.type === 'mode') {
    const next = { ...s, scanIndex: 0 }
    return [next, s.phase === 'wheel' ? [announceAt(s.path, ctx)] : []]
  }
  if (a.type === 'tick') {
    if (s.phase !== 'spell' && ctx.mode !== 'scan') return [s, []]
    const t = targets(s, ctx)
    const scanIndex = (s.scanIndex + 1) % t.length
    const next = { ...s, scanIndex }
    return [next, [aid(label(t[scanIndex], next, ctx))]]
  }

  const c = a.command
  if (c === 'HELP') return [s, [{ kind: 'help' }]]
  if (s.phase === 'spell') return spellCommand(s, c, ctx)
  if (ctx.mode === 'scan' && c === 'SELECT') return pickTarget(s, ctx)

  const dir = LOOKS[c]
  if (s.phase === 'readback') {
    if (c === 'SELECT') return confirm(s, ctx)
    if (dir || c === 'BACK') return cancel(s)
    return [s, []]
  }
  if (dir) return lookAt(s, dir, ctx)
  if (c === 'ACCEPT') return accept(s, ctx)
  if (c === 'SELECT') return finish(s)
  if (c === 'BACK') return [{ ...s, path: back(s.path), scanIndex: 0 }, [announceAt(back(s.path), ctx)]]
  return [s, []]
}
