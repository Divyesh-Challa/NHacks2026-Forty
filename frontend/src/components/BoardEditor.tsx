// Caregiver phrase-board editor. Saving PUTs the boards; the backend pushes them live to the patient.
// Styles: pages/caregiver.css (.cg-board*, .cg-phrases, .cg-savebar).
import { useEffect, useRef, useState } from 'react'
import type { Board } from '../lib/types'

interface Phrase {
  k: number // stable React key, so typing never remounts the input
  v: string
}
interface Draft {
  k: number
  id: string
  title: string
  phrases: Phrase[]
  open: boolean
}
type Status = 'idle' | 'saving' | 'saved' | 'failed'

let keySeq = 0
const nextKey = () => ++keySeq
const toDraft = (b: Board, open = false): Draft => ({
  k: nextKey(),
  id: b.id,
  title: b.title,
  phrases: b.items.map((v) => ({ k: nextKey(), v })),
  open,
})
const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'board'

/** The boards a save would send: untitled and empty boards dropped, phrases trimmed, ids unique. */
function toBoards(drafts: Draft[]): Board[] {
  const used = new Set<string>()
  return drafts
    .filter((d) => d.title.trim())
    .map((d) => {
      let id = d.id || slug(d.title)
      while (used.has(id)) id += '-2'
      used.add(id)
      const items = d.phrases.map((p) => p.v.trim()).filter(Boolean)
      return { id, title: d.title.trim(), items }
    })
    .filter((b) => b.items.length)
}

const Chevron = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M6 9l6 6 6-6" />
  </svg>
)
const Cross = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
    <path d="M6 6l12 12M18 6L6 18" />
  </svg>
)

export function BoardEditor({ boards, onSave }: { boards: Board[]; onSave: (b: Board[]) => Promise<void> }) {
  const [drafts, setDrafts] = useState<Draft[]>(() => boards.map((b, i) => toDraft(b, i === 0)))
  const [status, setStatus] = useState<Status>('idle')
  const focusKey = useRef<string | null>(null)

  // Reset the drafts when a new boards list arrives (adjusting state during render, not in an effect).
  // Boards the caregiver had open stay open (matched by id, else by position).
  const [seen, setSeen] = useState(boards)
  if (seen !== boards) {
    setSeen(boards)
    setDrafts((prev) =>
      boards.map((b, i) => toDraft(b, (prev.find((p) => p.id === b.id) ?? (prev.length === boards.length ? prev[i] : undefined))?.open ?? i === 0)),
    )
  }

  // Focus the input a button just created (new phrase / new board).
  useEffect(() => {
    if (!focusKey.current) return
    document.querySelector<HTMLInputElement>(`[data-fk="${focusKey.current}"]`)?.focus()
    focusKey.current = null
  }, [drafts])

  const edit = (fn: (d: Draft[]) => Draft[]) => {
    setDrafts(fn)
    setStatus('idle')
  }
  const patch = (i: number, p: Partial<Draft>) => edit((d) => d.map((x, j) => (j === i ? { ...x, ...p } : x)))
  // Expanding or collapsing a board is not an edit: it must not wipe "Saving…" / "Saved" / "Save failed".
  const toggle = (i: number) => setDrafts((d) => d.map((x, j) => (j === i ? { ...x, open: !x.open } : x)))
  const setPhrase = (i: number, k: number, v: string) =>
    patch(i, { phrases: drafts[i].phrases.map((p) => (p.k === k ? { ...p, v } : p)) })
  const addPhrase = (i: number, after?: number) => {
    const np: Phrase = { k: nextKey(), v: '' }
    const list = drafts[i].phrases
    const at = after === undefined ? list.length : list.findIndex((p) => p.k === after) + 1
    focusKey.current = `p${np.k}`
    patch(i, { phrases: [...list.slice(0, at), np, ...list.slice(at)] })
  }

  const out = toBoards(drafts)
  const dirty = JSON.stringify(out) !== JSON.stringify(toBoards(boards.map((b) => toDraft(b))))

  // A board with phrases but no name would be dropped by toBoards(): block the save instead of deleting it silently.
  const nameless = drafts.flatMap((d, i) => (!d.title.trim() && d.phrases.some((p) => p.v.trim()) ? [i + 1] : []))

  const save = () => {
    if (nameless.length) return
    setStatus('saving')
    onSave(out)
      .then(() => setStatus('saved'))
      .catch(() => setStatus('failed'))
  }

  const blocked = nameless.length
    ? `${nameless.length === 1 ? `Board ${nameless[0]} has` : `Boards ${nameless.join(', ')} have`} phrases but no name. Name ${nameless.length === 1 ? 'it' : 'them'} to save.`
    : ''
  const message =
    status === 'saving' ? 'Saving…'
    : blocked ? blocked
    : status === 'saved' ? 'Saved. The patient screen updated.'
    : status === 'failed' ? 'Save failed. Try again.'
    : dirty ? 'Unsaved changes' : 'Matches the patient screen'
  const tone = status === 'saving' ? '' : blocked ? 'fail' : status === 'saved' ? 'ok' : status === 'failed' ? 'fail' : dirty ? 'dirty' : ''

  return (
    <div className="cg-editor-wrap cg-editor-body">
      <div className="cg-boards">
        {!drafts.length && (
          <div className="cg-empty">
            <strong>No boards yet</strong>
            Add a board and its phrases, then save to send them to the patient screen.
          </div>
        )}
        {drafts.map((d, i) => {
          const n = d.phrases.filter((p) => p.v.trim()).length
          return (
            <section key={d.k} className="cg-board">
              <button className="cg-board-head" aria-expanded={d.open} onClick={() => toggle(i)}>
                <span className="t">
                  <b>{d.title.trim() || 'Untitled board'}</b>
                  {!d.title.trim() && n ? (
                    <small className="need">Needs a name</small>
                  ) : (
                    <small>{n} {n === 1 ? 'phrase' : 'phrases'}</small>
                  )}
                </span>
                <Chevron />
              </button>
              {d.open && (
                <div className="cg-board-body">
                  <label className="cg-field">
                    Board name
                    <input
                      value={d.title}
                      onChange={(e) => patch(i, { title: e.target.value })}
                      data-fk={`t${d.k}`}
                      aria-label="Board title"
                      aria-invalid={!d.title.trim() && n > 0}
                    />
                  </label>
                  <div className="cg-field">
                    Phrases
                    <ul className="cg-phrases">
                      {d.phrases.map((p, j) => (
                        <li key={p.k}>
                          <input
                            className="cg-input"
                            value={p.v}
                            data-fk={`p${p.k}`}
                            placeholder="Type a phrase"
                            aria-label={`${d.title} phrase ${j + 1}`}
                            onChange={(e) => setPhrase(i, p.k, e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                e.preventDefault()
                                addPhrase(i, p.k)
                              }
                            }}
                          />
                          <button
                            className="cg-x"
                            aria-label={`Remove phrase ${p.v || j + 1}`}
                            onClick={() => patch(i, { phrases: d.phrases.filter((x) => x.k !== p.k) })}
                          >
                            <Cross />
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div className="cg-board-actions">
                    <button className="cg-btn quiet" onClick={() => addPhrase(i)}>+ Add phrase</button>
                    <button className="cg-btn text" onClick={() => edit((x) => x.filter((_, j) => j !== i))}>Remove board</button>
                  </div>
                </div>
              )}
            </section>
          )
        })}
      </div>
      <button
        className="cg-btn quiet block cg-add-board"
        onClick={() => {
          const nd: Draft = { k: nextKey(), id: '', title: 'New board', phrases: [{ k: nextKey(), v: '' }], open: true }
          focusKey.current = `t${nd.k}`
          edit((d) => [...d, nd])
        }}
      >
        + Add board
      </button>
      <div className="cg-savebar">
        <button className="cg-btn primary block" onClick={save} disabled={status === 'saving' || nameless.length > 0} aria-describedby="cg-save-msg">
          Save and send to patient
        </button>
        <p id="cg-save-msg" className={`cg-save-status ${tone}`} role="status">{message}</p>
      </div>
    </div>
  )
}
