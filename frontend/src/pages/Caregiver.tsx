// Caregiver screen (mobile-friendly): login, live alerts, history, phrase editor, reliability chart.
import { useCallback, useEffect, useRef, useState } from 'react'
import { BoardEditor } from '../components/BoardEditor'
import { alertsUnlocked, playHelpAlert, unlockAlerts } from '../lib/alertSound'
import { ReliabilityChart, type ReliabilityPoint } from '../components/ReliabilityChart'
import { getBoards, getConfig, getMessages, login, putBoards, Unauthorized, type HistoryItem } from '../lib/api'
import type { Board, ModeChangeEvent, ServerEvent } from '../lib/types'
import { connect } from '../lib/ws'

type Tab = 'alerts' | 'history' | 'boards' | 'signals'
type FeedItem = HistoryItem | ModeChangeEvent
const MAX_POINTS = 180 // ~3 min at one reliability reading per second


function describe(ev: FeedItem): string {
  if (ev.type === 'alert') return `⚠ ${ev.message}`
  if (ev.type === 'spoken') return `Said: “${ev.text}”`
  return `Controls changed: ${ev.reason}`
}

function Login({ onLogin }: { onLogin: (token: string, patientId: string) => void }) {
  const [email, setEmail] = useState('caregiver@example.com')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  return (
    <main className="caregiver">
      <h1>Caregiver login</h1>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          unlockAlerts() // this tap is what lets the phone play the HELP sound later
          login(email, password)
            .then((r) => onLogin(r.token, r.patient_id))
            .catch(() => setError('Login failed'))
        }}
      >
        <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" autoComplete="username" />
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
          autoComplete="current-password"
        />
        <button type="submit">Log in</button>
        {error && <p className="error">{error}</p>}
      </form>
    </main>
  )
}

export default function Caregiver() {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('relay_token'))
  const [patientId, setPatientId] = useState(() => localStorage.getItem('relay_patient') ?? 'p1')
  const [tab, setTab] = useState<Tab>('alerts')
  const [live, setLive] = useState<FeedItem[]>([])
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [boards, setBoards] = useState<Board[]>([])
  const [points, setPoints] = useState<ReliabilityPoint[]>([])
  const [mode, setMode] = useState<string>('')
  const [cutoff, setCutoff] = useState(0.6)
  const [connected, setConnected] = useState(false)
  const [urgent, setUrgent] = useState(false)
  const [soundOn, setSoundOn] = useState(alertsUnlocked)
  const [notifyState, setNotifyState] = useState(() =>
    !window.isSecureContext || !('Notification' in window) ? 'unavailable' : Notification.permission,
  )

  const enableAlerts = () => {
    unlockAlerts()
    setSoundOn(true)
    if (notifyState === 'default') Notification.requestPermission().then(setNotifyState)
  }
  const tabRef = useRef(tab)
  tabRef.current = tab

  const logout = useCallback(() => {
    localStorage.removeItem('relay_token')
    setToken(null)
  }, [])

  const onAuthError = useCallback((e: unknown) => {
    if (e instanceof Unauthorized) logout()
  }, [logout])

  useEffect(() => {
    if (!token) return
    getMessages(patientId, token).then(setHistory).catch(onAuthError)
    getBoards(patientId).then(setBoards).catch(() => {})
    getConfig()
      .then((c) => setCutoff(c.input.reliability_cutoff))
      .catch(() => {})
  }, [token, patientId, onAuthError])

  useEffect(() => {
    if (!token) return
    const s = connect(
      `/ws/caregiver/${patientId}?token=${encodeURIComponent(token)}`,
      (ev: ServerEvent) => {
        if (ev.type === 'alert') {
          playHelpAlert()
          setUrgent(true)
          if (window.isSecureContext && 'Notification' in window && Notification.permission === 'granted')
            new Notification('Relay: HELP requested', { body: 'Your patient needs help now.', requireInteraction: true })
        }
        if (ev.type === 'alert' || ev.type === 'spoken') setHistory((h) => [ev, ...h])
        if (ev.type === 'alert' || ev.type === 'spoken' || ev.type === 'mode_change') setLive((f) => [ev, ...f].slice(0, 50))
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

  const tabs: [Tab, string][] = [['alerts', 'Live'], ['history', 'History'], ['boards', 'Boards'], ['signals', 'Signals']]

  return (
    <main className="caregiver">
      <header className="cg-header">
        <h1>Relay</h1>
        <span className="muted">{connected ? 'Connected' : 'Reconnecting…'}</span>
        <button className="link" onClick={logout}>Log out</button>
      </header>

      {(!soundOn || notifyState === 'default') && (
        <button className="enable-alerts" onClick={enableAlerts}>
          🔔 Tap to enable HELP alert sound{notifyState === 'default' ? ' and notifications' : ''}
        </button>
      )}
      {notifyState === 'unavailable' && (
        <p className="muted small">
          Phone notifications need HTTPS. Start the frontend with <code>make frontend-https</code>. Sound and
          vibration still work.
        </p>
      )}

      {urgent && (
        <button className="urgent-banner" onClick={() => setUrgent(false)}>
          ⚠ HELP requested. Tap to acknowledge.
        </button>
      )}

      <nav className="tabs">
        {tabs.map(([t, label]) => (
          <button key={t} className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>{label}</button>
        ))}
      </nav>

      {tab === 'alerts' && (
        <ul className="feed">
          {!live.length && <li className="muted">No activity yet. HELP alerts sound here.</li>}
          {live.map((ev, i) => (
            <li key={i} className={ev.type === 'alert' ? 'urgent' : ''}>{describe(ev)}</li>
          ))}
        </ul>
      )}

      {tab === 'history' && (
        <ul className="feed">
          {!history.length && <li className="muted">No messages yet.</li>}
          {history.map((ev, i) => (
            <li key={i} className={ev.type === 'alert' ? 'urgent' : ''}>
              <span className="time">{new Date(ev.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
              {describe(ev)}
            </li>
          ))}
        </ul>
      )}

      {tab === 'boards' && (
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
      )}

      {tab === 'signals' && (
        <section>
          <p className="muted">Mode: {mode || '—'}. Relay switches a control when its signal stays below the line.</p>
          <ReliabilityChart points={points} cutoff={cutoff} />
        </section>
      )}
    </main>
  )
}
