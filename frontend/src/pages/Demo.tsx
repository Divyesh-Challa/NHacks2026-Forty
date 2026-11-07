// Presenter control panel for the stage demo. Open on a separate laptop/phone, not the projector.
// Triggers /demo/degrade and shows live reliability, mode and mapping from the backend.
import { useEffect, useState } from 'react'
import { degrade } from '../lib/api'
import type { ModeChangeEvent, ReliabilityEvent } from '../lib/types'
import { connect } from '../lib/ws'

const PATIENT_ID = 'p1'
const SIGNALS = ['eog_h', 'blink', 'jaw'] as const
const LABELS: Record<string, string> = { eog_h: 'Eye movement', blink: 'Blink', jaw: 'Jaw' }

export default function Demo() {
  const [rel, setRel] = useState<ReliabilityEvent | null>(null)
  const [changes, setChanges] = useState<ModeChangeEvent[]>([])
  const [connected, setConnected] = useState(false)
  const [last, setLast] = useState('')

  useEffect(() => {
    const s = connect(
      `/ws/patient/${PATIENT_ID}`, // same reliability + mode_change events, no caregiver token needed
      (ev) => {
        if (ev.type === 'reliability') setRel(ev)
        else if (ev.type === 'mode_change') setChanges((c) => [ev, ...c].slice(0, 5))
      },
      setConnected,
    )
    return () => s.close()
  }, [])

  const run = (label: string, calls: [Parameters<typeof degrade>[0], number][]) => {
    Promise.all(calls.map(([s, f]) => degrade(s, f)))
      .then(() => setLast(label))
      .catch(() => setLast(`${label} failed — is the backend + signal service running?`))
  }

  return (
    <main className="caregiver demo">
      <h1>Demo controls</h1>
      <p className="muted">{connected ? 'Connected' : 'Backend offline'} · patient {PATIENT_ID}</p>

      <div className="demo-buttons">
        <button onClick={() => run('Eyes degraded', [['eye', 0.3]])}>Degrade eyes → jaw scan</button>
        <button onClick={() => run('Eye movement degraded', [['eog_h', 0.3]])}>Degrade eye movement only</button>
        <button className="secondary" onClick={() => run('Restored', [['eye', 1], ['jaw', 1]])}>Restore all</button>
      </div>
      {last && <p>{last}. Remap takes ~10 readings.</p>}

      <h2>Mode: {rel?.mode ?? '—'}</h2>
      <p className="muted">
        {rel ? Object.entries(rel.mapping).map(([cmd, g]) => `${cmd} = ${g}`).join(' · ') : 'No reliability yet'}
      </p>
      {SIGNALS.map((s) => {
        const r = rel?.signals[s]
        return (
          <div key={s} className="meter">
            <span>{LABELS[s]}</span>
            <div className="bar">
              <div className={`fill ${r !== undefined && r < 0.6 ? 'low' : ''}`} style={{ width: `${(r ?? 0) * 100}%` }} />
            </div>
            <span>{r !== undefined ? `${Math.round(r * 100)}%` : '—'}</span>
          </div>
        )
      })}

      <h2>Recent switches</h2>
      <ul className="feed">
        {changes.map((c, i) => (
          <li key={i}>{c.from} → {c.to}: {c.reason}</li>
        ))}
      </ul>
    </main>
  )
}
