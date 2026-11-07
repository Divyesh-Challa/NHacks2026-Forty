import { test } from 'node:test'
import assert from 'node:assert/strict'
import { normalizeEvent } from './normalize.ts'

test("the backend's old 'split' mode reads as 'wheel'", () => {
  const change = normalizeEvent({ type: 'mode_change', from: 'split', to: 'scan', reason: 'r' })
  assert.equal(change.type === 'mode_change' && change.from, 'wheel')
  const rel = normalizeEvent({ type: 'reliability', signals: {}, mode: 'split', mapping: {} })
  assert.equal(rel.type === 'reliability' && rel.mode, 'wheel')
})

test('other events pass through unchanged', () => {
  const ev = { type: 'command', command: 'LEFT', via: 'eog_h', confidence: 0.9, ts: 1 }
  assert.deepEqual(normalizeEvent(ev), ev)
})
