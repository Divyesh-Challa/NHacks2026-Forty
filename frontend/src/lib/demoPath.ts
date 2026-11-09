// Guided demo: only the next step toward one target sentence is accepted; every other look is ignored.
// The gestures are still real, so a miss just means "try again". The path is found by searching the
// real wheel machine, so it can't drift from the tree. Keys 1-9 pick a scenario, 0 turns the guide off.
import type { Command } from './types.ts'
import { step } from './wheelMachine.ts'
import type { Ctx, MachineState } from './wheelMachine.ts'

// Key 1..9 = DEMO_SCENARIOS[0..8]. Exact spoken text from the wheel tree (checked by the test).
export const DEMO_SCENARIOS = [
  'I need water.',
  'I want soup.',
  "I don't want juice.",
  "I'm in pain.",
  'Please call the nurse.',
  'I need the bathroom.',
  "I'm too cold.",
  'Thank you.',
  'Yes.',
]
const MOVES: Command[] = ['UP', 'RIGHT', 'DOWN', 'LEFT', 'SELECT']
const key = (s: MachineState) => `${s.phase}|${s.readback?.kind ?? ''}|${s.path.map((p) => `${p.dir}:${p.node.word}`).join('>')}`

/** First command of the shortest way from `from` to speaking `target` (null if unreachable). */
export function nextToward(from: MachineState, ctx: Ctx, target: string): Command | null {
  const seen = new Set([key(from)])
  let queue: { s: MachineState; first: Command | null }[] = [{ s: from, first: null }]
  while (queue.length) {
    const next: typeof queue = []
    for (const { s, first } of queue) {
      for (const c of MOVES) {
        const [n, fx] = step(s, { type: 'command', command: c }, ctx)
        const f = first ?? c
        if (fx.some((e) => e.kind === 'say' && e.text === target)) return f
        if (!seen.has(key(n))) {
          seen.add(key(n))
          next.push({ s: n, first: f })
        }
      }
    }
    queue = next
  }
  return null
}

/** Should this command reach the machine? HELP always does; in scan mode only SELECT exists anyway. */
export function allowed(c: Command, s: MachineState, ctx: Ctx, target: string): boolean {
  if (c === 'HELP' || ctx.mode === 'scan') return true
  return c === nextToward(s, ctx, target)
}
