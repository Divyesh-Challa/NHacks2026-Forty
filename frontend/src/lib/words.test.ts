import { test } from 'node:test'
import assert from 'node:assert/strict'
import { learn, loadWords, saveWords, suggest } from './words.ts'

const DAY = 86_400_000
const K = 'Food › I want'

test('learn trims and adds a new link', () => {
  assert.deepEqual(learn([], K, ' video game ', 1), [{ key: K, word: 'video game', count: 1, last: 1 }])
})

test('learning the same word again (any case) bumps its count', () => {
  const links = learn(learn([], K, 'video game', 1), K, 'Video Game', 2)
  assert.equal(links.length, 1)
  assert.equal(links[0].count, 2)
  assert.equal(links[0].last, 2)
})

test('learning a blank word changes nothing', () => {
  const links = learn([], K, 'x', 1)
  assert.equal(learn(links, K, '   ', 3), links)
})

test('suggest falls back to an ancestor key', () => {
  const links = learn([], K, 'video game', 1)
  assert.equal(suggest(links, ['Food › I want › Drinks', K, 'Food'], 1), 'video game')
})

test('recent use outweighs old use', () => {
  const now = 100 * DAY
  const links = [
    { key: K, word: 'old', count: 4, last: now - 21 * DAY }, // 4 × 0.5³ = 0.5
    { key: K, word: 'new', count: 1, last: now },
  ]
  assert.equal(suggest(links, [K], now), 'new')
})

test('no links means no suggestion', () => {
  assert.equal(suggest([], ['x'], 0), null)
})

test('bad or blocked storage loads as empty and never throws', () => {
  const g = globalThis as { localStorage?: unknown }
  g.localStorage = { getItem: () => 'not json', setItem: () => {} }
  assert.deepEqual(loadWords('p1'), [])
  g.localStorage = {
    getItem: () => {
      throw new Error('blocked')
    },
    setItem: () => {
      throw new Error('blocked')
    },
  }
  assert.deepEqual(loadWords('p1'), [])
  assert.doesNotThrow(() => saveWords('p1', []))
  delete g.localStorage
})
