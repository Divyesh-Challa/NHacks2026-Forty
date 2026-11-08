// Spelling: LetterBoard shows the word being built; LetterGrid shows the letters the scan steps through.
import { ScanTimer } from './RadialWheel'

// Items that start with a symbol (speak, delete, space) are actions, not letters; show them as words.
const isAction = (item: string) => /^[^\p{L}]/u.test(item)
const labelOf = (item: string) => item.replace(/^[^\p{L}]+/u, '')

export function LetterGrid({ items, active, intervalMs, epoch }: { items: string[]; active: number; intervalMs: number; epoch: number }) {
  return (
    <div className="letters">
      {items.map((item, i) => (
        <div key={item} className={`letter${isAction(item) ? ' action' : ''}${i === active ? ' active' : ''}`}>
          {labelOf(item)}
          {i === active && <ScanTimer ms={intervalMs} epoch={epoch} />}
        </div>
      ))}
    </div>
  )
}

export function LetterBoard({ text }: { text: string }) {
  return (
    <div className="letter-buffer" aria-live="polite">
      {text ? <span className="typed">{text}</span> : <span className="muted">Spell a word…</span>}
      <span className="caret" />
    </div>
  )
}
