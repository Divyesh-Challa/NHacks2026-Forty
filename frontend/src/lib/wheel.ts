// Radial wheel: a tree of words in four fixed directions. Pure logic, no React — tested in wheel.test.ts.
// Spec: docs/superpowers/specs/2026-11-07-radial-wheel-design.md
//
// A path is the list of picks so far. The picked slot keeps its word and stays where it is; the
// other three directions show its children. Looking at the kept slot again goes back a level.

export type Dir = 'up' | 'right' | 'down' | 'left'
export const DIRS: Dir[] = ['up', 'right', 'down', 'left'] // clockwise; also the scan order

export interface WheelNode {
  word: string // shown on the slot and read by the aid
  phrase?: string // form inside a sentence ("a drink"); default word.toLowerCase()
  template?: string // starters only: "I want {x}."
  say?: string // full sentence for a leaf with no starter above it
  spell?: true // the Spell… slot
  learned?: true // a learned word placed in the centre
  help?: true // the HELP slot: looking at it asks to send an alert (confirmed with SELECT)
  children?: Partial<Record<Dir, WheelNode>>
}

export interface Pick {
  dir: Dir | 'centre'
  node: WheelNode
}

export interface WheelView {
  slots: Record<Dir, WheelNode | null>
  kept: Dir | null
  picked: Dir | 'centre' | null
}

const hasChildren = (n: WheelNode) => !!n.children && Object.keys(n.children).length > 0
const leafPicked = (path: Pick[]) => path.length > 0 && !hasChildren(path[path.length - 1].node)
// Index of the pick that owns the level on screen (-1 = the root).
const ownerIndex = (path: Pick[]) => path.length - (leafPicked(path) ? 2 : 1)

export function view(root: WheelNode, path: Pick[]): WheelView {
  const o = ownerIndex(path)
  const owner = o >= 0 ? path[o] : null
  const base = (owner ? owner.node.children : root.children) ?? {}
  const slots = Object.fromEntries(DIRS.map((d) => [d, base[d] ?? null])) as Record<Dir, WheelNode | null>
  // Owners always have children, so they were picked from a direction, never the centre.
  if (owner) slots[owner.dir as Dir] = owner.node
  return {
    slots,
    kept: (owner?.dir as Dir | undefined) ?? null,
    picked: leafPicked(path) ? path[path.length - 1].dir : null,
  }
}

export function look(root: WheelNode, path: Pick[], dir: Dir): Pick[] {
  const v = view(root, path)
  if (v.picked !== null) {
    if (dir === v.picked) return path.slice(0, -1)
    if (dir === v.kept) return path.slice(0, -2)
    const node = v.slots[dir]
    return node ? [...path.slice(0, -1), { dir, node }] : path
  }
  if (dir === v.kept) return path.slice(0, -1)
  const node = v.slots[dir]
  return node ? [...path, { dir, node }] : path
}

export const back = (path: Pick[]): Pick[] => path.slice(0, -1)

export function sentence(path: Pick[]): string | null {
  const nodes = path.map((p) => p.node)
  if (!nodes.length) return null
  const i = nodes.findLastIndex((n) => n.template)
  if (i === -1) return nodes[nodes.length - 1].say ?? null
  const x = nodes.length - 1 > i ? nodes[nodes.length - 1] : nodes[i - 1]
  if (!x) return null
  return nodes[i].template!.replace('{x}', x.phrase ?? x.word.toLowerCase())
}

// Keys for learned words: the owner path, then each ancestor. Never the root ('').
export function keyChain(path: Pick[]): string[] {
  const chain = path.slice(0, ownerIndex(path) + 1).map((p) => p.node.word)
  return chain.map((_, k) => chain.slice(0, chain.length - k).join(' › '))
}

// Children of a node picked from `from` fill the other three directions, clockwise from up.
export function branch(from: Dir, nodes: (WheelNode | null)[]): Partial<Record<Dir, WheelNode>> {
  const out: Partial<Record<Dir, WheelNode>> = {}
  DIRS.filter((d) => d !== from).forEach((d, i) => {
    if (nodes[i]) out[d] = nodes[i]!
  })
  return out
}

export function validateTree(root: WheelNode): string[] {
  const errors: string[] = []
  const walk = (node: WheelNode, from: Dir | null, at: string) => {
    for (const [d, child] of Object.entries(node.children ?? {}) as [Dir, WheelNode][]) {
      const here = at ? `${at} › ${child.word}` : child.word
      if (d === from) errors.push(`${here}: sits in its parent's own direction (${d})`)
      walk(child, d, here)
    }
  }
  walk(root, null, '')
  return errors
}
