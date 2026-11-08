import { test } from 'node:test'
import assert from 'node:assert/strict'
import { keyChain, look, sentence, validateTree, view } from './wheel.ts'
import type { Dir, Pick, WheelNode } from './wheel.ts'
import { WHEEL } from './wheelTree.ts'

const go = (...dirs: Dir[]): Pick[] => dirs.reduce<Pick[]>((path, d) => look(WHEEL, path, d), [])
const words = (v: ReturnType<typeof view>) => Object.fromEntries(Object.entries(v.slots).map(([d, n]) => [d, n?.word ?? null]))

test('seed tree is valid', () => {
  assert.deepEqual(validateTree(WHEEL), [])
})

test('root shows the four topics with nothing kept', () => {
  const v = view(WHEEL, [])
  assert.deepEqual(words(v), { up: 'Food', right: 'Needs', down: 'Feelings', left: 'Yes / No' })
  assert.equal(v.kept, null)
})

test('picked slot stays and the rest follow from it', () => {
  const v = view(WHEEL, go('up'))
  assert.deepEqual(words(v), { up: 'Food', right: 'I want', down: "I don't want", left: 'I need' })
  assert.equal(v.kept, 'up')
  const items = view(WHEEL, go('up', 'right', 'up'))
  assert.equal(items.kept, 'up')
  assert.deepEqual(words(items), { up: 'Drinks', right: 'Water', down: 'Juice', left: 'Spell…' })
})

test('looking at the kept slot goes back', () => {
  assert.deepEqual(go('up', 'up'), [])
})

test('a picked leaf can be unpicked or swapped', () => {
  const path = go('up', 'right', 'up', 'right')
  assert.equal(view(WHEEL, path).picked, 'right')
  assert.equal(look(WHEEL, path, 'right').length, 3)
  const swapped = look(WHEEL, path, 'down')
  assert.equal(swapped.at(-1)?.node.word, 'Juice')
})

test('looking at an empty slot does nothing', () => {
  assert.equal(go('right', 'down', 'left').length, 2) // Needs › People has nothing on the left
})

test('Yes / No has HELP on the right', () => {
  assert.equal(go('left', 'right').at(-1)?.node.help, true)
})

test('sentences from templates', () => {
  assert.equal(sentence(go('up', 'right')), 'I want food.')
  assert.equal(sentence(go('up', 'right', 'up')), 'I want a drink.')
  assert.equal(sentence(go('up', 'right', 'up', 'right')), 'I want water.')
  // From "I don't want", down is the kept slot, so Meals sits right.
  assert.equal(sentence(go('up', 'down', 'right', 'up')), "I don't want soup.")
  assert.equal(sentence(go('left', 'up')), 'Yes.')
  assert.equal(sentence(go('left', 'down')), 'No.')
  assert.equal(sentence(go('up')), null)
  assert.equal(sentence([]), null)
})

test('keyChain lists the owner path then its ancestors', () => {
  assert.deepEqual(keyChain(go('up', 'right', 'up')), ['Food › I want › Drinks', 'Food › I want', 'Food'])
  assert.deepEqual(keyChain([]), [])
})

test('validateTree catches a child in its parent direction', () => {
  const bad: WheelNode = { word: '', children: { up: { word: 'A', children: { up: { word: 'B' } } } } }
  assert.equal(validateTree(bad).length, 1)
})
