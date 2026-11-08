// Learned words: links from a wheel path to a word the person added ("Food › I want" → "video game").
// The centre slot suggests the strongest link for the current path, weighted toward recent use.
// ponytail: stored in this browser only; moves to the backend words API in the follow-up task.

export interface WordLink {
  key: string
  word: string
  count: number
  last: number // ms epoch
}

export const HALF_LIFE_DAYS = 7
const DAY_MS = 86_400_000

export function learn(links: WordLink[], key: string, word: string, now: number): WordLink[] {
  const w = word.trim()
  if (!w) return links
  const i = links.findIndex((l) => l.key === key && l.word.toLowerCase() === w.toLowerCase())
  if (i === -1) return [...links, { key, word: w, count: 1, last: now }]
  return links.map((l, j) => (j === i ? { ...l, count: l.count + 1, last: now } : l))
}

export function suggest(links: WordLink[], keys: string[], now: number): string | null {
  const score = (l: WordLink) => l.count * 0.5 ** ((now - l.last) / DAY_MS / HALF_LIFE_DAYS)
  for (const key of keys) {
    const here = links.filter((l) => l.key === key)
    if (!here.length) continue
    here.sort((a, b) => score(b) - score(a) || b.last - a.last)
    return here[0].word
  }
  return null
}

const storageKey = (patientId: string) => `relay_words_${patientId}`

export function loadWords(patientId: string): WordLink[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(storageKey(patientId)) ?? '[]')
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function saveWords(patientId: string, links: WordLink[]): void {
  try {
    localStorage.setItem(storageKey(patientId), JSON.stringify(links))
  } catch {
    // Blocked storage: the words still work for this session.
  }
}
