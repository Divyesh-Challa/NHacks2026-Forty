// Caregiver phrase-board editor. Saving PUTs the boards; the backend pushes them live to the patient.
import { useState } from 'react'
import type { Board } from '../lib/types'

interface Draft {
  id: string
  title: string
  text: string // one phrase per line
}

const toDraft = (b: Board): Draft => ({ id: b.id, title: b.title, text: b.items.join('\n') })
const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'board'

export function BoardEditor({ boards, onSave }: { boards: Board[]; onSave: (b: Board[]) => Promise<void> }) {
  const [drafts, setDrafts] = useState<Draft[]>(boards.map(toDraft))
  const [status, setStatus] = useState('')

  // Reset the drafts when a new boards list arrives (adjusting state during render, not in an effect).
  const [seen, setSeen] = useState(boards)
  if (seen !== boards) {
    setSeen(boards)
    setDrafts(boards.map(toDraft))
  }

  const update = (i: number, patch: Partial<Draft>) =>
    setDrafts((d) => d.map((x, j) => (j === i ? { ...x, ...patch } : x)))

  const save = () => {
    const used = new Set<string>()
    const out: Board[] = drafts
      .filter((d) => d.title.trim())
      .map((d) => {
        let id = d.id || slug(d.title)
        while (used.has(id)) id += '-2'
        used.add(id)
        const items = d.text.split('\n').map((s) => s.trim()).filter(Boolean)
        return { id, title: d.title.trim(), items }
      })
      .filter((b) => b.items.length)
    setStatus('Saving…')
    onSave(out)
      .then(() => setStatus('Saved. The patient screen updated.'))
      .catch(() => setStatus('Save failed. Try again.'))
  }

  return (
    <div className="editor">
      {drafts.map((d, i) => (
        <section key={i} className="board-draft">
          <div className="row">
            <input value={d.title} onChange={(e) => update(i, { title: e.target.value })} aria-label="Board title" />
            <button className="secondary" onClick={() => setDrafts((x) => x.filter((_, j) => j !== i))}>Remove</button>
          </div>
          <textarea
            rows={Math.max(3, d.text.split('\n').length)}
            value={d.text}
            onChange={(e) => update(i, { text: e.target.value })}
            aria-label={`${d.title} phrases, one per line`}
          />
        </section>
      ))}
      <button className="secondary" onClick={() => setDrafts((d) => [...d, { id: '', title: 'New board', text: '' }])}>
        + Add board
      </button>
      <div className="save-bar">
        <button onClick={save}>Save and send to patient</button>
        {status && <p className="muted small">{status}</p>}
      </div>
    </div>
  )
}
