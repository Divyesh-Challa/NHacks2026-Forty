// Split mode (2+ reliable gestures): LEFT/RIGHT halves the candidates until one remains.
// Owner: Role C. SCAFFOLD: working halving logic, minimal styling.
import { useEffect, useState } from 'react'
import type { Command } from '../lib/types'

export interface BoardProps {
  items: string[]
  command: { command: Command; id: number } | null
  onSelect: (item: string) => void
}

export function SplitBoard({ items, command, onSelect }: BoardProps) {
  const [range, setRange] = useState<[number, number]>([0, items.length])

  useEffect(() => setRange([0, items.length]), [items])

  useEffect(() => {
    if (!command) return
    const [lo, hi] = range
    const mid = Math.ceil((lo + hi) / 2)
    let next: [number, number] = range
    if (command.command === 'LEFT') next = [lo, mid]
    else if (command.command === 'RIGHT') next = [mid, hi]
    else if (command.command === 'BACK') next = [0, items.length]
    else return
    if (next[1] - next[0] === 1) {
      onSelect(items[next[0]])
      next = [0, items.length]
    }
    setRange(next)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [command])

  const [lo, hi] = range
  const mid = Math.ceil((lo + hi) / 2)
  return (
    <div className="split">
      <div className="half">{items.slice(lo, mid).map((i) => <div key={i} className="item">{i}</div>)}</div>
      <div className="half">{items.slice(mid, hi).map((i) => <div key={i} className="item">{i}</div>)}</div>
    </div>
  )
}
