// Scan mode (1 reliable gesture): highlight auto-advances; the gesture = SELECT.
// Owner: Role C. SCAFFOLD: working auto-advance; BACK/HELP are appended by the page.
import { useEffect, useState } from 'react'
import type { BoardProps } from './SplitBoard'

export function ScanBoard({ items, command, onSelect, intervalMs }: BoardProps & { intervalMs: number }) {
  const [index, setIndex] = useState(0)

  useEffect(() => setIndex(0), [items])

  useEffect(() => {
    const t = setInterval(() => setIndex((i) => (i + 1) % items.length), intervalMs)
    return () => clearInterval(t)
  }, [items, intervalMs])

  useEffect(() => {
    if (command?.command === 'SELECT') onSelect(items[index])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [command])

  return (
    <div className="scan">
      {items.map((item, i) => (
        <div key={item} className={`item ${i === index ? 'active' : ''}`}>{item}</div>
      ))}
    </div>
  )
}
