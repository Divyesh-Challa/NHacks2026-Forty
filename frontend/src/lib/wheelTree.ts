// Seed vocabulary for the radial wheel. Synthetic demo data.
// Below the root every node is built for the direction it was picked from, so its children fill
// the other three directions (see branch() in wheel.ts) and positions never clash.
import { branch, DIRS } from './wheel.ts'
import type { Dir, WheelNode } from './wheel.ts'

type Make = (from: Dir) => WheelNode

export const SPELL: WheelNode = { word: 'Spell…', spell: true }

const leaf = (word: string, extra: Partial<WheelNode> = {}): Make => () => ({ word, ...extra })
const say = (word: string, text: string) => leaf(word, { say: text })
const spell: Make = () => SPELL
const node =
  (word: string, extra: Partial<WheelNode>, kids: (Make | null)[]): Make =>
  (from) => {
    const dirs = DIRS.filter((d) => d !== from)
    return { word, ...extra, children: branch(from, kids.map((k, i) => k?.(dirs[i]) ?? null)) }
  }

const groups = [
  node('Drinks', { phrase: 'a drink' }, [leaf('Water', { phrase: 'water' }), leaf('Juice', { phrase: 'juice' }), spell]),
  node('Meals', { phrase: 'a meal' }, [leaf('Soup', { phrase: 'soup' }), leaf('Toast', { phrase: 'toast' }), spell]),
  node('Snacks', { phrase: 'a snack' }, [leaf('Fruit', { phrase: 'fruit' }), leaf('Crackers', { phrase: 'crackers' }), spell]),
]

const food = node('Food', {}, [
  node('I want', { template: 'I want {x}.' }, groups),
  node("I don't want", { template: "I don't want {x}." }, groups),
  node('I need', { template: 'I need {x}.' }, groups),
])

const needs = node('Needs', {}, [
  node('Body', {}, [
    say('Reposition me', 'Please reposition me.'),
    say("I'm in pain", "I'm in pain."),
    node('Temperature', {}, [say('Too hot', "I'm too hot."), say('Too cold', "I'm too cold.")]),
  ]),
  node('People', {}, [say('Family', 'Please call my family.'), say('Nurse', 'Please call the nurse.')]),
  say('Bathroom', 'I need the bathroom.'),
])

const feelings = node('Feelings', {}, [
  say('Happy', "I'm happy."),
  say('Tired', "I'm tired."),
  node('More', {}, [say('Frustrated', "I'm frustrated."), say('Thank you', 'Thank you.'), say('Love you', 'I love you.')]),
])

// Picked from the left: Yes up, HELP right, No down.
const helpSlot = leaf('HELP', { help: true })
const yesNo = node('Yes / No', {}, [say('Yes', 'Yes.'), helpSlot, say('No', 'No.')])

export const WHEEL: WheelNode = {
  word: '',
  children: { up: food('up'), right: needs('right'), down: feelings('down'), left: yesNo('left') },
}
