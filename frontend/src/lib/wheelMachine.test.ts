import { test } from 'node:test'
import assert from 'node:assert/strict'
import { INITIAL, step, targets } from './wheelMachine.ts'
import type { Action, Ctx, Effect, MachineState } from './wheelMachine.ts'
import type { Command } from './types.ts'
import { SPELL_ITEMS } from './spell.ts'
import { WHEEL } from './wheelTree.ts'

const base: Ctx = { root: WHEEL, mode: 'wheel', suggestFor: () => null }
const scan: Ctx = { ...base, mode: 'scan' }
const cmd = (command: Command): Action => ({ type: 'command', command })
const tick: Action = { type: 'tick' }
const ticksTo = (item: string): Action[] => Array(SPELL_ITEMS.indexOf(item)).fill(tick)

function run(actions: Action[], ctx = base, start: MachineState = INITIAL) {
  let s = start
  const effects: Effect[] = []
  for (const a of actions) {
    const [next, fx] = step(s, a, ctx)
    s = next
    effects.push(...fx)
  }
  return { s, effects }
}
const says = (fx: Effect[]) => fx.filter((e) => e.kind === 'say')
const water = [cmd('UP'), cmd('RIGHT'), cmd('UP'), cmd('RIGHT'), cmd('SELECT')]

test('"I want water" is read back, then spoken only on the second SELECT', () => {
  const first = run(water)
  assert.equal(first.s.phase, 'readback')
  assert.equal(says(first.effects).length, 0)
  const readbackAid = first.effects.find((e) => e.kind === 'aid' && e.text.includes('I want water'))
  assert.ok(readbackAid && readbackAid.kind === 'aid' && readbackAid.always === true)

  const done = run([cmd('SELECT')], base, first.s)
  assert.deepEqual(says(done.effects), [{ kind: 'say', text: 'I want water.', path: ['Food', 'I want', 'Drinks', 'Water'] }])
  assert.deepEqual(done.s, INITIAL)
})

test('SELECT with nothing picked does not read back', () => {
  const { s, effects } = run([cmd('SELECT')])
  assert.equal(s.phase, 'wheel')
  assert.equal(says(effects).length, 0)
})

test('a look during read-back cancels without speaking; ACCEPT is ignored', () => {
  const rb = run(water).s
  const cancelled = run([cmd('LEFT')], base, rb)
  assert.equal(cancelled.s.phase, 'wheel')
  assert.equal(cancelled.s.path.length, 4)
  assert.equal(says(cancelled.effects).length, 0)
  assert.equal(step(rb, cmd('ACCEPT'), base)[0], rb)
})

test('spelling a new word saves it under the path and places it in the centre', () => {
  const spelling = run([cmd('UP'), cmd('RIGHT'), cmd('UP'), cmd('LEFT')])
  assert.equal(spelling.s.phase, 'spell')
  const typed = run([...ticksTo('V'), cmd('SELECT'), ...ticksTo('I'), cmd('SELECT'), cmd('SELECT')], base, spelling.s)
  assert.deepEqual(typed.s.readback, { kind: 'word', text: 'VI' })
  const saved = run([cmd('SELECT')], base, typed.s)
  assert.deepEqual(
    saved.effects.filter((e) => e.kind === 'learn'),
    [{ kind: 'learn', key: 'Food › I want › Drinks', word: 'VI' }],
  )
  assert.equal(saved.s.phase, 'wheel')
  assert.equal(saved.s.path.at(-1)?.dir, 'centre')
})

test('Speak with nothing spelled returns to the wheel and learns nothing', () => {
  const spelling = run([cmd('UP'), cmd('RIGHT'), cmd('UP'), cmd('LEFT')]).s
  const { s, effects } = run([cmd('SELECT')], base, spelling)
  assert.equal(s.phase, 'wheel')
  assert.equal(effects.filter((e) => e.kind === 'learn').length, 0)
})

test('looks during spelling do nothing', () => {
  const spelling = run([cmd('UP'), cmd('RIGHT'), cmd('UP'), cmd('LEFT')]).s
  assert.equal(step(spelling, cmd('LEFT'), base)[0], spelling)
  assert.equal(step(spelling, cmd('UP'), base)[0], spelling)
})

test('an accepted suggestion is spoken and counted', () => {
  const ctx: Ctx = { ...base, suggestFor: () => 'video game' }
  const { effects } = run([cmd('UP'), cmd('RIGHT'), cmd('ACCEPT'), cmd('SELECT'), cmd('SELECT')], ctx)
  assert.equal(says(effects)[0]?.text, 'I want video game.')
  assert.deepEqual(
    effects.filter((e) => e.kind === 'learn'),
    [{ kind: 'learn', key: 'Food › I want', word: 'video game' }],
  )
})

test('scan mode steps through the wheel targets', () => {
  assert.deepEqual(targets(INITIAL, scan), ['up', 'right', 'down', 'left', 'help'])
  const { s } = run([tick, cmd('SELECT')], scan)
  assert.equal(s.path[0]?.node.word, 'Needs')
  const rb = run([cmd('UP'), cmd('RIGHT'), cmd('SELECT')]).s
  assert.deepEqual(targets(rb, scan), ['speak', 'cancel'])
})

test('switching mode keeps the half-built path', () => {
  const half = run([cmd('UP'), cmd('RIGHT')]).s
  const { s } = run([{ type: 'mode' }], scan, { ...half, scanIndex: 2 })
  assert.equal(s.path.length, 2)
  assert.equal(s.scanIndex, 0)
})

test('HELP works in every phase and changes nothing else', () => {
  const phases = [INITIAL, run(water).s, run([cmd('UP'), cmd('RIGHT'), cmd('UP'), cmd('LEFT')]).s]
  for (const s of phases) {
    const [next, fx] = step(s, cmd('HELP'), base)
    assert.equal(next, s)
    assert.deepEqual(fx, [{ kind: 'help' }])
  }
})
