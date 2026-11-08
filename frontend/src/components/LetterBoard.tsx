// Spelling: LetterBoard shows the word being built; LetterGrid shows the letters the scan steps through.
export function LetterGrid({ items, active }: { items: string[]; active: number }) {
  return (
    <div className="scan letters">
      {items.map((item, i) => (
        <div key={item} className={`item${i === active ? ' active' : ''}`}>
          {item}
        </div>
      ))}
    </div>
  )
}

export function LetterBoard({ text }: { text: string }) {
  return (
    <div className="letter-buffer" aria-live="polite">
      {text || <span className="muted">Spell a word…</span>}
      <span className="caret" />
    </div>
  )
}
