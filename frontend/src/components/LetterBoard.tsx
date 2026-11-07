// Spelling: letters are ordinary board items (see lib/spell.ts); this component only shows the word being built.
export function LetterBoard({ text }: { text: string }) {
  return (
    <div className="letter-buffer" aria-live="polite">
      {text || <span className="muted">Spell a message…</span>}
      <span className="caret" />
    </div>
  )
}
