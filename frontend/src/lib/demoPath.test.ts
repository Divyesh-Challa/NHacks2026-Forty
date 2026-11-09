import { test } from 'node:test'
import assert from 'node:assert/strict'
import { allowed, DEMO_SCENARIOS, nextToward } from './demoPath.ts'
import { INITIAL, step } from './wheelMachine.ts'
import type { Ctx } from './wheelMachine.ts'
import { WHEEL } from './wheelTree.ts'

const DEMO_SENTENCE = DEMO_SCENARIOS[0]
const ctx: Ctx = { root: WHEEL, mode: 'wheel', suggestFor: () => null }

test('following only the allowed commands speaks the target sentence', () => {
  let s = INITIAL
  const said: string[] = []
  for (let i = 0; i < 12 && !said.length; i++) {
    const c = nextToward(s, ctx, DEMO_SENTENCE)!
    assert.ok(c, 'path exists')
    const [n, fx] = step(s, { type: 'command', command: c }, ctx)
    s = n
    said.push(...fx.flatMap((e) => (e.kind === 'say' ? [e.text] : [])))
  }
  assert.deepEqual(said, [DEMO_SENTENCE])
})

test('off-path looks are ignored, HELP always passes, scan mode is untouched', () => {
  const first = nextToward(INITIAL, ctx, DEMO_SENTENCE)!
  const wrong = (['UP', 'RIGHT', 'DOWN', 'LEFT', 'SELECT'] as const).find((c) => c !== first)!
  assert.equal(allowed(first, INITIAL, ctx, DEMO_SENTENCE), true)
  assert.equal(allowed(wrong, INITIAL, ctx, DEMO_SENTENCE), false)
  assert.equal(allowed('HELP', INITIAL, ctx, DEMO_SENTENCE), true)
  assert.equal(allowed(wrong, INITIAL, { ...ctx, mode: 'scan' }, DEMO_SENTENCE), true)
})

test('every scenario is reachable and speaks exactly its sentence', () => {
  for (const target of DEMO_SCENARIOS) {
    let s = INITIAL
    const said: string[] = []
    for (let i = 0; i < 14 && !said.length; i++) {
      const c = nextToward(s, ctx, target)
      assert.ok(c, `no path to "${target}"`)
      const [n, fx] = step(s, { type: 'command', command: c }, ctx)
      s = n
      said.push(...fx.flatMap((e) => (e.kind === 'say' ? [e.text] : [])))
    }
    assert.deepEqual(said, [target])
  }
})
