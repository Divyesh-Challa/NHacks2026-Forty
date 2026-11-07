// Spelling: letters are ordinary board items (frequency-ordered so common letters take fewer
// split-mode halvings); this component only shows the word being built.
export const SPELL_SPEAK = '🔊 Speak'
export const SPELL_DELETE = '⌫ Delete'
export const SPELL_SPACE = '␣ Space'
export const SPELL_ITEMS = [SPELL_SPEAK, SPELL_DELETE, SPELL_SPACE, ...'ETAOINSHRDLUCMWFGYPBVKJXQZ'.split('')]

export function LetterBoard({ text }: { text: string }) {
  return (
    <div className="letter-buffer" aria-live="polite">
      {text || <span className="muted">Spell a message…</span>}
      <span className="caret" />
    </div>
  )
}
