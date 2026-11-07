import { test } from 'node:test'
import assert from 'node:assert/strict'
import { FlickDetector } from './flickSim.ts'

test('a flick fires once, then needs a return to centre', () => {
  const f = new FlickDetector({ flickPx: 160, rearmPx: 50 })
  assert.equal(f.move(200, 0), null) // not armed until the cursor has been near the centre
  assert.equal(f.move(0, 0), null)
  assert.equal(f.move(200, 0), 'right')
  assert.equal(f.move(250, 0), null)
  assert.equal(f.move(10, 10), null)
  assert.equal(f.move(0, -200), 'up') // screen y points down
  f.move(0, 0)
  assert.equal(f.move(150, 170), 'down') // dominant axis wins
  f.move(0, 0)
  assert.equal(f.move(-170, 20), 'left')
})
