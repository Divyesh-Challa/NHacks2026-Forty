import { test } from 'node:test'
import assert from 'node:assert/strict'

// Minimal stand-ins for the browser speech and audio APIs.
const log: string[] = []
const synth = {
  speaking: false,
  cancel: () => log.push('cancel'),
  speak: (u: { text: string }) => log.push(`speak ${u.text}`),
}
let resumed = 0
class FakeAudio {
  state = 'suspended'
  currentTime = 0
  destination = {}
  resume() {
    resumed++
    this.state = 'running'
    return Promise.resolve()
  }
  createOscillator() {
    return { frequency: {}, connect: (g: unknown) => g, start() {}, stop() {} }
  }
  createGain() {
    return { gain: {}, connect: (d: unknown) => d }
  }
}
class FakeUtterance {
  text: string
  volume = 1
  rate = 1
  onend: (() => void) | null = null
  onerror: (() => void) | null = null
  constructor(text: string) {
    this.text = text
  }
}
Object.assign(globalThis, {
  window: { speechSynthesis: synth },
  speechSynthesis: synth,
  SpeechSynthesisUtterance: FakeUtterance,
  AudioContext: FakeAudio,
})
const { aid, speak } = await import('./tts.ts')

test('a later aid does not cut off the read-back', () => {
  log.length = 0
  aid('I want water.', true)
  synth.speaking = true
  aid('cancel')
  assert.deepEqual(log, ['cancel', 'speak I want water.', 'speak cancel'])
  synth.speaking = false
})

test('the aid tone wakes a suspended audio context', () => {
  aid('up Food')
  assert.ok(resumed >= 1)
})

test('the aid comes back once the real voice has stopped, even without onend', () => {
  speak('I want water.') // onend never fires
  synth.speaking = true
  log.length = 0
  aid('up Food')
  assert.deepEqual(log, []) // real voice still talking: aid stays quiet
  synth.speaking = false
  aid('up Food')
  assert.ok(log.includes('speak up Food'))
})
