// Caregiver screen (mobile-friendly): login, live alerts, history, phrase editor, reliability chart.
// Styles live in ./caregiver.css (same look as the /demo console: true-black, yellow data, red for HELP only).
import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { BoardEditor } from '../components/BoardEditor'
import { alertsUnlocked, playHelpAlert, unlockAlerts } from '../lib/alertSound'
import { ReliabilityChart, type ReliabilityPoint } from '../components/ReliabilityChart'
import { getBoards, getConfig, getMessages, login, putBoards, Unauthorized, type HistoryItem } from '../lib/api'
import type { Board, ModeChangeEvent, ServerEvent } from '../lib/types'
import { connect } from '../lib/ws'
import './caregiver.css'

type Tab = 'alerts' | 'history' | 'boards' | 'signals'
type FeedItem = HistoryItem | ModeChangeEvent
interface FeedRow {
  ev: FeedItem
  at: number // ms since epoch: the event's own timestamp, or arrival time for mode changes
}
const MAX_POINTS = 180 // ~3 min at one reliability reading per second
const MODE_LABEL: Record<string, string> = { wheel: 'Wheel mode', scan: 'Scan mode' }
const MODE_HINT: Record<string, string> = {
  wheel: 'Four eye directions pick a slot.',
  scan: 'One gesture selects the highlighted item.',
}

const clock = (ms: number) => new Date(ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
const dayLabel = (ms: number) => {
  const d = new Date(ms)
  const today = new Date()
  const yesterday = new Date()
  yesterday.setDate(today.getDate() - 1)
  if (d.toDateString() === today.toDateString()) return 'Today'
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday'
  return d.toLocaleDateString([], { weekday: 'long', month: 'short', day: 'numeric' })
}

const TAB_HASH: Record<string, Tab> = { live: 'alerts', history: 'history', phrases: 'boards', signals: 'signals' }
const tabFromHash = (): Tab => TAB_HASH[window.location.hash.slice(1)] ?? 'alerts'

function Brand() {
  return (
    <span className="cg-brand">
      <span className="cg-mark" aria-hidden="true">R</span>
      <span className="cg-name">Relay</span>
    </span>
  )
}

const ICONS: Record<Tab, ReactNode> = {
  alerts: <path d="M12 3a6 6 0 0 0-6 6c0 5-2 6.5-2 6.5h16S18 14 18 9a6 6 0 0 0-6-6ZM10 19a2 2 0 0 0 4 0" />,
  history: <path d="M12 7v5l3 2M3.5 12a8.5 8.5 0 1 0 2.6-6.1L3.5 8.5M3.5 4v4.5H8" />,
  boards: <path d="M5 6h14M5 12h14M5 18h9" />,
  signals: <path d="M4 19V5M4 19h16M8 15l4-5 3 3 5-7" />,
}

function TabIcon({ tab }: { tab: Tab }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {ICONS[tab]}
    </svg>
  )
}

function Row({ row }: { row: FeedRow }) {
  const { ev, at } = row
  let tag: string
  let text: string
  if (ev.type === 'alert') {
    tag = 'HELP request'
    text = ev.message === 'HELP' ? 'Your patient asked for help' : ev.message
  } else if (ev.type === 'spoken') {
    tag = 'Said aloud'
    text = `“${ev.text}”`
  } else {
    tag = 'Controls changed'
    text = ev.reason
  }
  return (
    <li className={`cg-row ${ev.type}`}>
      <div className="meta">
        <span className="tag">{tag}</span>
        <time dateTime={new Date(at).toISOString()}>{clock(at)}</time>
      </div>
      <span className="text">{text}</span>
    </li>
  )
}

function Login({ onLogin }: { onLogin: (token: string, patientId: string) => void }) {
  const [email, setEmail] = useState('caregiver@example.com')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  return (
    <main className="cg cg-login">
      <div className="cg-login-box">
        <Brand />
        <h1>Caregiver sign in</h1>
        <p className="cg-lede">Get HELP alerts on this phone, see what your person has said, and edit their phrase boards.</p>
        <form
          className="cg-form"
          onSubmit={(e) => {
            e.preventDefault()
            unlockAlerts() // this tap is what lets the phone play the HELP sound later
            setBusy(true)
            login(email, password)
              .then((r) => onLogin(r.token, r.patient_id))
              .catch(() => {
                setError('Login failed')
                setBusy(false)
              })
          }}
        >
          <label className="cg-field">
            Email
            <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" autoComplete="username" inputMode="email" />
          </label>
          <label className="cg-field">
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              autoComplete="current-password"
            />
          </label>
          {error && (
            <p className="cg-error error" role="alert">
              <strong>{error}</strong>. Check your email and password and try again.
            </p>
          )}
          <button type="submit" className="cg-btn primary block" disabled={busy}>
            {busy ? 'Signing in…' : 'Log in'}
          </button>
        </form>
        <p className="cg-fine">Demo build. Synthetic patient data only.</p>
      </div>
    </main>
  )
}

export default function Caregiver() {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('relay_token'))
  const [patientId, setPatientId] = useState(() => localStorage.getItem('relay_patient') ?? 'p1')
  const [tab, setTab] = useState<Tab>(tabFromHash) // /caregiver#signals opens straight on a tab
  const [live, setLive] = useState<FeedRow[]>([])
  const [history, setHistory] = useState<FeedRow[]>([])
  const [historyState, setHistoryState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [reload, setReload] = useState(0)
  const [boards, setBoards] = useState<Board[]>([])
  const [points, setPoints] = useState<ReliabilityPoint[]>([])
  const [mode, setMode] = useState<string>('')
  const [cutoff, setCutoff] = useState(0.6)
  const [connected, setConnected] = useState(false)
  const [urgentAt, setUrgentAt] = useState<number | null>(null)
  const [soundOn, setSoundOn] = useState(alertsUnlocked)
  const [notifyState, setNotifyState] = useState(() =>
    !window.isSecureContext || !('Notification' in window) ? 'unavailable' : Notification.permission,
  )

  const enableAlerts = () => {
    unlockAlerts()
    setSoundOn(true)
    if (notifyState === 'default') Notification.requestPermission().then(setNotifyState)
  }
  const logout = useCallback(() => {
    localStorage.removeItem('relay_token')
    setToken(null)
  }, [])

  const onAuthError = useCallback((e: unknown) => {
    if (e instanceof Unauthorized) logout()
  }, [logout])

  useEffect(() => {
    if (!token) return
    getMessages(patientId, token)
      .then((h) => {
        setHistory(h.map((ev) => ({ ev, at: ev.ts })))
        setHistoryState('ready')
      })
      .catch((e) => {
        onAuthError(e)
        setHistoryState('error')
      })
    getBoards(patientId).then(setBoards).catch(() => {})
    getConfig()
      .then((c) => setCutoff(c.input.reliability_cutoff))
      .catch(() => {})
  }, [token, patientId, onAuthError, reload])

  useEffect(() => {
    if (!token) return
    const s = connect(
      `/ws/caregiver/${patientId}?token=${encodeURIComponent(token)}`,
      (ev: ServerEvent) => {
        if (ev.type === 'alert') {
          playHelpAlert()
          setUrgentAt(typeof ev.ts === 'number' ? ev.ts : Date.now())
          if (window.isSecureContext && 'Notification' in window && Notification.permission === 'granted')
            new Notification('Relay: HELP requested', { body: 'Your patient needs help now.', requireInteraction: true })
        }
        if (ev.type === 'alert' || ev.type === 'spoken') setHistory((h) => [{ ev, at: ev.ts }, ...h])
        if (ev.type === 'alert' || ev.type === 'spoken' || ev.type === 'mode_change')
          setLive((f) => [{ ev, at: 'ts' in ev ? ev.ts : Date.now() }, ...f].slice(0, 50))
        if (ev.type === 'reliability') {
          setMode(ev.mode)
          setPoints((p) => [...p, { t: Date.now(), signals: ev.signals }].slice(-MAX_POINTS))
        }
      },
      setConnected,
    )
    return () => s.close()
  }, [token, patientId])

  if (!token) {
    return (
      <Login
        onLogin={(t, pid) => {
          localStorage.setItem('relay_token', t)
          localStorage.setItem('relay_patient', pid)
          setSoundOn(true) // the login tap unlocked audio
          setPatientId(pid)
          setToken(t)
        }}
      />
    )
  }

  const tabs: [Tab, string][] = [['alerts', 'Live'], ['history', 'History'], ['boards', 'Phrases'], ['signals', 'Signals']]
  const lastHelp = live.find((r) => r.ev.type === 'alert')
  const needsSetup = !soundOn || notifyState === 'default'
  const modeKnown = mode in MODE_LABEL

  // Alert card headline: connection first, because "all quiet" while disconnected would be a lie.
  const status = !connected
    ? { cls: 'warn', head: 'Reconnecting…', sub: 'HELP alerts cannot reach this phone until the connection returns.' }
    : urgentAt
      ? { cls: 'help', head: 'HELP requested', sub: `At ${clock(urgentAt)}. Tap the red bar to acknowledge.` }
      : lastHelp
        ? { cls: '', head: `Last HELP ${clock(lastHelp.at)}`, sub: 'Acknowledged. You will be alerted again if there is another.' }
        : { cls: '', head: 'No HELP requests', sub: 'This phone will sound and vibrate the moment one arrives.' }

  return (
    <div className="cg">
      <header className="cg-top">
        <div className="cg-top-in">
          <Brand />
          <span className={`cg-status ${connected ? 'on' : 'off'}`} role="status">
            <span className="dot" aria-hidden="true" />
            {connected ? 'Connected' : 'Reconnecting…'}
          </span>
          <button className="cg-btn text" onClick={logout}>Log out</button>
        </div>
      </header>

      {urgentAt && (
        <button className="cg-help" onClick={() => setUrgentAt(null)}>
          <span className="cg-help-in">
            <span className="cg-help-kicker">HELP requested</span>
            <span className="cg-help-sub">Patient {patientId} needs you now · {clock(urgentAt)}</span>
            <span className="cg-help-ack">Tap to acknowledge</span>
          </span>
        </button>
      )}

      <main className="cg-main">
        <div className="cg-title">
          <h1>Patient {patientId} · demo</h1>
          <p className={connected ? '' : 'warn'}>
            {!connected
              ? 'Reconnecting. HELP alerts are paused.'
              : modeKnown
                ? `Controls are in ${mode} mode.`
                : 'Waiting for the first signal reading.'}
          </p>
        </div>

        <nav className="cg-tabs" aria-label="Sections">
          {tabs.map(([t, label]) => (
            <button key={t} aria-current={tab === t ? 'page' : undefined} onClick={() => {
                setTab(t)
                window.scrollTo(0, 0)
              }}>
              <TabIcon tab={t} />
              {label}
              {t === 'alerts' && urgentAt && tab !== 'alerts' && <span className="pip" aria-label="HELP waiting" />}
            </button>
          ))}
        </nav>

        {needsSetup && (
          <div className={`cg-setup${tab === 'alerts' ? '' : ' slim'}`}>
            {tab === 'alerts' && (
              <p>
                <strong>HELP alerts are not fully on</strong>
                {notifyState === 'default'
                  ? 'Allow sound and notifications so a HELP request reaches you even when this screen is off.'
                  : 'Allow sound so a HELP request is heard on this phone.'}
              </p>
            )}
            <button className="cg-btn primary block enable-alerts" onClick={enableAlerts}>
              Tap to enable HELP alert sound{notifyState === 'default' ? ' and notifications' : ''}
            </button>
          </div>
        )}

        <div className="cg-panel">
          {tab === 'alerts' && (
            <div className="cg-live">
              <section className="cg-card status" aria-labelledby="st-h">
                <h2 id="st-h">HELP alerts</h2>
                <div aria-live="polite">
                  <p className={`cg-figure ${status.cls}`}>{status.head}</p>
                  <p className="cg-figure-sub">{status.sub}</p>
                </div>
                <ul className="cg-ready">
                  <li>
                    Alert sound
                    <b className={soundOn ? '' : 'off'}>{soundOn ? 'On' : 'Tap to enable'}</b>
                  </li>
                  <li>
                    Notifications
                    <b className={notifyState === 'granted' ? '' : 'off'}>
                      {notifyState === 'granted' ? 'On' : notifyState === 'denied' ? 'Blocked in browser' : notifyState === 'unavailable' ? 'Needs HTTPS' : 'Tap to enable'}
                      {notifyState === 'unavailable' && <small>Sound and vibration still work.</small>}
                    </b>
                  </li>
                </ul>
              </section>

              <section className="feedcol cg-sec" aria-labelledby="live-h">
                <div className="cg-sec-head">
                  <h2 id="live-h">Recent activity</h2>
                  <span>This session</span>
                </div>
                {!live.length ? (
                  <div className="cg-empty">
                    <strong>No activity yet</strong>
                    Phrases your patient speaks, HELP requests and control changes show up here as they happen.
                  </div>
                ) : (
                  <ul className="cg-feed">
                    {live.map((r, i) => <Row key={`${r.at}-${r.ev.type}-${i}`} row={r} />)}
                  </ul>
                )}
              </section>
            </div>
          )}

          {tab === 'history' && (
            <section className="cg-sec" aria-labelledby="hist-h">
              <div className="cg-sec-head">
                <h2 id="hist-h">Messages and alerts</h2>
                {historyState === 'ready' && <span>{history.length} total</span>}
              </div>
              {historyState === 'loading' && !history.length ? (
                <div className="cg-empty">Loading history…</div>
              ) : historyState === 'error' && !history.length ? (
                <div className="cg-empty">
                  <strong>Couldn’t load history</strong>
                  The server did not answer. Your alerts still arrive live.
                  <br />
                  <button className="cg-btn quiet" onClick={() => {
                      setHistoryState('loading')
                      setReload((n) => n + 1)
                    }}>Try again</button>
                </div>
              ) : !history.length ? (
                <div className="cg-empty">
                  <strong>No messages yet</strong>
                  Everything your patient says and every HELP request is kept here.
                </div>
              ) : (
                <ul className="cg-feed">
                  {history.map((r, i) => {
                    const day = dayLabel(r.at)
                    const showDay = i === 0 || dayLabel(history[i - 1].at) !== day
                    return (
                      <FeedItemWithDay key={`${r.at}-${r.ev.type}-${i}`} day={showDay ? day : null} row={r} />
                    )
                  })}
                </ul>
              )}
            </section>
          )}

          {tab === 'boards' && (
            <section className="cg-sec cg-editor" aria-labelledby="ed-h">
              <div className="cg-sec-head">
                <h2 id="ed-h">Phrase boards</h2>
              </div>
              <p className="cg-intro">What the patient can choose from. Saving updates their screen right away.</p>
              <BoardEditor
                boards={boards}
                onSave={(b) =>
                  putBoards(patientId, b, token)
                    .then(setBoards)
                    .catch((e) => {
                      onAuthError(e)
                      throw e
                    })
                }
              />
            </section>
          )}

          {tab === 'signals' && (
            <section className="cg-sec" aria-labelledby="sig-h">
              <h2 id="sig-h" className="sr-only-h">Signals</h2>
              <p className="cg-mode">{modeKnown ? MODE_LABEL[mode] : 'No reading yet'}</p>
              <p className="cg-mode-sub">
                {modeKnown ? `${MODE_HINT[mode]} ` : ''}
                Relay switches a control when its signal stays below the line.
              </p>
              <ReliabilityChart points={points} cutoff={cutoff} />
            </section>
          )}
        </div>
      </main>
    </div>
  )
}

/** A history row, preceded by its day heading when the day changes. */
function FeedItemWithDay({ day, row }: { day: string | null; row: FeedRow }) {
  return (
    <>
      {day && <li className="cg-day" aria-hidden="true">{day}</li>}
      <Row row={row} />
    </>
  )
}
