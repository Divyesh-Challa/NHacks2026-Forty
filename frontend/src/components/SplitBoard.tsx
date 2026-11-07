// Split mode (2+ reliable gestures): LEFT/RIGHT halves the candidates until one remains.
// Owner: Role C. SCAFFOLD: working halving logic, minimal styling.
import { useEffect, useState } from 'react'
import type { Command } from '../lib/types'

export interface BoardProps {
  items: string[]
  command: { command: Command; id: number } | null
  onSelect: (item: string) => void
}

const DENSE_AT = 7 // more items than this in a half → wrap into a grid with smaller text

const itemClass = (item: string) => `item${item.includes('HELP') ? ' help' : ''}`

export function SplitBoard({
  items,
  command,
  onSelect,
  leftHint,
  rightHint,
}: BoardProps & { leftHint?: string; rightHint?: string }) {
  const [range, setRange] = useState<[number, number]>([0, items.length])
  // Reset only when the list's contents change, not on every new array from the parent.
  const itemsKey = items.join('\n')
  useEffect(() => setRange([0, items.length]), [itemsKey]) // eslint-disable-line react-hooks/exhaustive-deps

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
  const halves: [string[], string | undefined][] = [
    [items.slice(lo, mid), leftHint && `◀ ${leftHint}`],
    [items.slice(mid, hi), rightHint && `${rightHint} ▶`],
  ]
  return (
    <div className="split">
      {halves.map(([part, hint], side) => (
        <div key={side} className={`half${part.length > DENSE_AT ? ' dense' : ''}`}>
          {hint && <div className={`half-hint ${side ? 'right' : 'left'}`}>{hint}</div>}
          <div className="half-items">
            {part.map((i) => (
              <div key={i} className={itemClass(i)}>{i}</div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
