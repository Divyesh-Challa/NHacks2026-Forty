// Presenter console for the stage demo. Open on a separate laptop/phone, not the projector.
// Triggers /demo/degrade and shows live mode, mapping and reliability from the backend, plus a
// countdown to the next remap computed with the same rule as the input manager.
import { useEffect, useRef, useState } from 'react'
import { degrade, getConfig } from '../lib/api'
import type { CommandEvent, ModeChangeEvent, ReliabilityEvent } from '../lib/types'
import { connect } from '../lib/ws'
import './demo.css'

const PATIENT_ID = 'p1'
const SIGNALS = ['eog_h', 'blink', 'jaw'] as const
const COMMANDS = ['LEFT', 'RIGHT', 'UP', 'DOWN', 'SELECT', 'ACCEPT', 'BACK', 'HELP'] as const
const LABELS: Record<string, string> = { eog_h: 'Eye movement', eog_v: 'Eye up/down', blink: 'Blink', jaw: 'Jaw', brow: 'Eyebrow' }
const GESTURES: Record<string, string> = {
  look_left: 'Look left',
  look_right: 'Look right',
  look_up: 'Look up',
  look_down: 'Look down',
  blink_double: 'Double blink',
  jaw_clench: 'Jaw clench',
  jaw_hold: 'Jaw hold',
  brow_raise: 'Eyebrow raise',
}
// Gesture -> the signal that produces it (mirrors GESTURE_SOURCE in backend/app/input_manager.py).
const SOURCE: Record<string, string> = {
  look_left: 'eog_h',
  look_right: 'eog_h',
  look_up: 'eog_v',
  look_down: 'eog_v',
  blink_double: 'blink',
  jaw_clench: 'jaw',
  jaw_hold: 'jaw',
  brow_raise: 'brow',
}
// Fallbacks until GET /config answers; the backend's values win.
const DEFAULT_RULES = { reliability_cutoff: 0.6, recover_cutoff: 0.75, remap_window: 10, recover_window: 20 }

type Rules = typeof DEFAULT_RULES
// Consecutive readings below the switch cutoff / at or above the recover cutoff, per signal.
type Streaks = Record<string, { low: number; high: number }>

const pct = (r: number) => `${Math.round(r * 100)}%`
const clock = (ts: number) => new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })

export default function Demo() {
  const [rel, setRel] = useState<ReliabilityEvent | null>(null)
  const [streaks, setStreaks] = useState<Streaks>({})
  const [changes, setChanges] = useState<(ModeChangeEvent & { at: number })[]>([])
  const [lastCmd, setLastCmd] = useState<(CommandEvent & { at: number }) | null>(null)
  const [connected, setConnected] = useState(false)
  const [rules, setRules] = useState<Rules>(DEFAULT_RULES)
  const [busy, setBusy] = useState(false)
  const [last, setLast] = useState<{ text: string; ok: boolean } | null>(null)
  const rulesRef = useRef(rules)

  useEffect(() => {
    getConfig()
      .then((c) => {
        const next = { ...DEFAULT_RULES, ...c.input }
        rulesRef.current = next
        setRules(next)
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    const s = connect(
      `/ws/patient/${PATIENT_ID}`, // same reliability + mode_change events, no caregiver token needed
      (ev) => {
        if (ev.type === 'reliability') {
          setRel(ev)
          const { reliability_cutoff, recover_cutoff } = rulesRef.current
          setStreaks((prev) => {
            const next: Streaks = {}
            for (const [sig, r] of Object.entries(ev.signals)) {
              const p = prev[sig] ?? { low: 0, high: 0 }
              next[sig] = { low: r < reliability_cutoff ? p.low + 1 : 0, high: r >= recover_cutoff ? p.high + 1 : 0 }
            }
            return next
          })
        } else if (ev.type === 'mode_change') setChanges((c) => [{ ...ev, at: Date.now() }, ...c].slice(0, 6))
        else if (ev.type === 'command') setLastCmd({ ...ev, at: Date.now() })
      },
      setConnected,
    )
    return () => s.close()
  }, [])

  const run = (label: string, calls: [Parameters<typeof degrade>[0], number][]) => {
    setBusy(true)
    Promise.all(calls.map(([s, f]) => degrade(s, f)))
      .then(() => setLast({ text: `${label} at ${clock(Date.now())}.`, ok: true }))
      .catch(() => setLast({ text: `${label} failed. Is the backend running (make backend)?`, ok: false }))
      .finally(() => setBusy(false))
  }

  const mapping = (rel?.mapping ?? {}) as Record<string, string>
  const inUse = new Set(Object.values(mapping).map((g) => SOURCE[g]))
  const signals = rel ? [...new Set([...SIGNALS, ...Object.keys(rel.signals)])] : [...SIGNALS]
  const scanDone = rel?.mode === 'scan'
  const finding = describe(rel, streaks, inUse, rules, changes[0], connected)

  return (
    <div className="console">
      <header className="con-top">
        <span className="con-mark" aria-hidden="true">R</span>
        <span className="con-name">Relay</span>
        <nav className="con-links" aria-label="Other screens">
          <a href={`/patient/${PATIENT_ID}`} target="_blank" rel="noreferrer">Patient screen</a>
          <a href="/caregiver" target="_blank" rel="noreferrer">Caregiver</a>
        </nav>
        <span className={`con-status ${connected ? 'on' : 'off'}`}>
          <span className="dot" aria-hidden="true" />
          {connected ? 'Live' : 'Backend offline'} · patient {PATIENT_ID}
        </span>
      </header>

      <main className="con-main">
        <div className="con-title">
          <h1>Stage console</h1>
          <p className={`con-finding ${finding.tone}`} aria-live="polite">{finding.text}</p>
        </div>

        <div className="con-grid">
          <section className="con-card con-now" aria-labelledby="now-h">
            <h2 id="now-h">Controls now</h2>
            {rel ? (
              <>
                <p className="mode-figure">
                  {rel.mode === 'wheel' ? 'Wheel mode' : 'Scan mode'}
                  <span>{rel.mode === 'wheel' ? 'four eye directions pick a slot' : 'one gesture selects the highlight'}</span>
                </p>
                <table className="mapping">
                  <thead>
                    <tr>
                      <th scope="col">Command</th>
                      <th scope="col">Gesture</th>
                      <th scope="col" className="col-signal">Signal</th>
                      <th scope="col" className="num">Reliability</th>
                    </tr>
                  </thead>
                  <tbody>
                    {COMMANDS.filter((c) => mapping[c] || c === 'SELECT').map((c) => {
                      const g = mapping[c]
                      const src = g ? SOURCE[g] : undefined
                      const r = src ? rel.signals[src] : undefined
                      return (
                        <tr key={c}>
                          <th scope="row">{c}</th>
                          <td>{g ? GESTURES[g] ?? g : <span className="dash">—</span>}</td>
                          <td className="col-signal">{src ? LABELS[src] ?? src : <span className="dash">—</span>}</td>
                          <td className={`num ${r !== undefined && r < rules.reliability_cutoff ? 'neg' : ''}`}>
                            {r !== undefined ? pct(r) : <span className="dash">—</span>}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
                <p className="con-meta">
                  {lastCmd ? (
                    <>
                      Last command <strong>{lastCmd.command}</strong> via {LABELS[lastCmd.via] ?? lastCmd.via} ·{' '}
                      {pct(lastCmd.confidence)} confident · {clock(lastCmd.at)}
                    </>
                  ) : (
                    'No commands yet.'
                  )}
                </p>
              </>
            ) : (
              <p className="con-empty">
                {connected ? 'Waiting for the first reliability reading. Start the signal service with make signal.' : 'Not connected. Start the backend with make backend; this page reconnects by itself.'}
              </p>
            )}
          </section>

          <section className="con-card con-run" aria-labelledby="run-h">
            <h2 id="run-h">Run sheet</h2>
            <ol className="steps">
              <li>
                <h3>Speak a phrase</h3>
                <p>Look left and right to reach “I need water”, accept a suggestion, Relay speaks it.</p>
                <a className="con-link" href={`/patient/${PATIENT_ID}`} target="_blank" rel="noreferrer">
                  Open patient screen
                </a>
              </li>
              <li>
                <h3>Lose the eyes</h3>
                <p>
                  {scanDone
                    ? 'Done. Relay is in scan mode; finish the next message with a jaw clench.'
                    : `Drops eye movement and blink to 30% gain. Relay switches after ${rules.remap_window} low readings.`}
                </p>
                <div className="actions">
                  <button className="primary" disabled={busy} onClick={() => run('Eyes degraded', [['eye', 0.3]])}>
                    Degrade eyes
                  </button>
                  <button className="quiet" disabled={busy} onClick={() => run('Eye movement degraded', [['eog_h', 0.3]])}>
                    Eye movement only
                  </button>
                </div>
              </li>
              <li>
                <h3>Call for help</h3>
                <p>Hold a jaw clench for 2 s, or hold H on the patient screen. The caregiver phone rings.</p>
                <a className="con-link" href="/caregiver" target="_blank" rel="noreferrer">
                  Open caregiver
                </a>
              </li>
            </ol>
            <div className="reset">
              <button className="quiet" disabled={busy} onClick={() => run('All signals restored', [['eye', 1], ['jaw', 1]])}>
                Restore all
              </button>
              <span>Back to wheel after {rules.recover_window} readings above {pct(rules.recover_cutoff)}.</span>
            </div>
            {last && (
              <p className={`con-result ${last.ok ? '' : 'neg'}`} role="status">
                {last.text}
              </p>
            )}
          </section>

          <section className="con-card con-signals" aria-labelledby="sig-h">
            <div className="card-head">
              <h2 id="sig-h">Signal reliability</h2>
              <ul className="key" aria-label="Key">
                <li><span className="sw in" />In use</li>
                <li><span className="sw idle" />Spare</li>
                <li><span className="sw low" />Below {pct(rules.reliability_cutoff)}</li>
              </ul>
            </div>
            <ul className="meters">
              {signals.map((s) => {
                const r = rel?.signals[s]
                const st = streaks[s] ?? { low: 0, high: 0 }
                const low = r !== undefined && r < rules.reliability_cutoff
                return (
                  <li key={s} className="meter-row">
                    <span className="m-label">{LABELS[s] ?? s}</span>
                    <span className="m-value">{r !== undefined ? pct(r) : <span className="dash">—</span>}</span>
                    <div
                      className="m-track"
                      role="meter"
                      aria-label={`${LABELS[s] ?? s} reliability`}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={r !== undefined ? Math.round(r * 100) : undefined}
                    >
                      <div className={`m-fill ${low ? 'low' : inUse.has(s) ? 'in' : 'idle'}`} style={{ width: `${(r ?? 0) * 100}%` }} />
                      <span className="m-mark" style={{ left: `${rules.reliability_cutoff * 100}%` }} title="Switch below" />
                      <span className="m-mark rec" style={{ left: `${rules.recover_cutoff * 100}%` }} title="Recover above" />
                    </div>
                    <span className="m-note">{streakNote(s, r, st, inUse, rules)}</span>
                  </li>
                )
              })}
            </ul>
          </section>

          <section className="con-card con-log" aria-labelledby="log-h">
            <h2 id="log-h">Switches</h2>
            {changes.length ? (
              <ul className="switches">
                {changes.map((c, i) => (
                  <li key={`${c.at}-${i}`}>
                    <span className="t">{clock(c.at)}</span>
                    <span>
                      <strong>
                        {c.from} → {c.to}
                      </strong>{' '}
                      {c.reason}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="con-empty">No switches since this page opened.</p>
            )}
          </section>
        </div>
      </main>
    </div>
  )
}

function streakNote(s: string, r: number | undefined, st: { low: number; high: number }, inUse: Set<string>, rules: Rules) {
  if (r === undefined) return 'No readings'
  if (inUse.has(s) && st.low > 0) return `Low ${Math.min(st.low, rules.remap_window)} of ${rules.remap_window}`
  if (!inUse.has(s) && st.high > 0 && st.high < rules.recover_window) return `Recovering ${st.high} of ${rules.recover_window}`
  if (!inUse.has(s) && r < rules.reliability_cutoff) return 'Not in use · too unreliable'
  return inUse.has(s) ? 'Steady' : 'Spare'
}

// The one line under the title: what the presenter needs to know right now.
function describe(
  rel: ReliabilityEvent | null,
  streaks: Streaks,
  inUse: Set<string>,
  rules: Rules,
  lastChange: (ModeChangeEvent & { at: number }) | undefined,
  connected: boolean,
): { text: string; tone: '' | 'warn' | 'neg' } {
  if (!connected) return { text: 'Backend offline. Start it with make backend; this page reconnects by itself.', tone: 'neg' }
  if (!rel) return { text: 'Connected. Waiting for the first reliability reading.', tone: '' }
  const falling = [...inUse]
    .map((s) => ({ s, low: streaks[s]?.low ?? 0, r: rel.signals[s] }))
    .filter((x) => x.low > 0 && x.low < rules.remap_window)
    .sort((a, b) => b.low - a.low)[0]
  if (falling) {
    const left = rules.remap_window - falling.low
    return {
      text: `${LABELS[falling.s] ?? falling.s} is at ${pct(falling.r)}, under ${pct(rules.reliability_cutoff)}. Relay switches after ${left} more low reading${left === 1 ? '' : 's'}.`,
      tone: 'warn',
    }
  }
  if (lastChange) return { text: `Switched to ${lastChange.to} at ${clock(lastChange.at)}. ${lastChange.reason}`, tone: '' }
  if (rel.mode === 'scan') {
    const select = rel.mapping.SELECT
    const lost = Object.entries(rel.signals)
      .filter(([, r]) => r < rules.reliability_cutoff)
      .map(([s]) => (LABELS[s] ?? s).toLowerCase())
    const list = lost.join(' and ')
    const why = lost.length ? ` ${list[0].toUpperCase()}${list.slice(1)} ${lost.length === 1 ? 'is' : 'are'} below ${pct(rules.reliability_cutoff)}.` : ''
    return { text: `Scan mode: ${select ? (GESTURES[select] ?? select).toLowerCase() : 'nothing'} selects.${why}`, tone: '' }
  }
  return { text: `All signals in use are above ${pct(rules.reliability_cutoff)}. Nothing will switch.`, tone: '' }
}
