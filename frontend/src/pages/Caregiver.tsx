// Caregiver screen (mobile-friendly): login, live alerts, history. Owner: Role D.
// SCAFFOLD: demo login + live feed with sound/Notification on HELP.
// TODO: message history (GET /patients/:id/messages), board editor (PUT boards), reliability chart.
import { useEffect, useState } from 'react'
import { login } from '../lib/api'
import type { ServerEvent } from '../lib/types'
import { connect } from '../lib/ws'

const PATIENT_ID = 'p1'

function beep() {
  const ctx = new AudioContext()
  const osc = ctx.createOscillator()
  osc.frequency.value = 880
  osc.connect(ctx.destination)
  osc.start()
  osc.stop(ctx.currentTime + 0.6)
}

export default function Caregiver() {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('relay_token'))
  const [email, setEmail] = useState('caregiver@example.com')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [feed, setFeed] = useState<ServerEvent[]>([])

  useEffect(() => {
    if (!token) return
    if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission()
    const s = connect(`/ws/caregiver/${PATIENT_ID}?token=${encodeURIComponent(token)}`, (ev) => {
      if (ev.type === 'alert') {
        beep()
        if ('Notification' in window && Notification.permission === 'granted') new Notification('Relay: HELP requested')
      }
      if (ev.type === 'alert' || ev.type === 'spoken' || ev.type === 'mode_change') setFeed((f) => [ev, ...f].slice(0, 50))
    })
    return () => s.close()
  }, [token])

  if (!token) {
    return (
      <main className="caregiver">
        <h1>Caregiver login</h1>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            login(email, password)
              .then((r) => {
                localStorage.setItem('relay_token', r.token)
                setToken(r.token)
              })
              .catch(() => setError('Login failed'))
          }}
        >
          <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" />
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" />
          <button type="submit">Log in</button>
          {error && <p className="error">{error}</p>}
        </form>
      </main>
    )
  }

  return (
    <main className="caregiver">
      <h1>Live feed</h1>
      <ul className="feed">
        {feed.map((ev, i) => (
          <li key={i} className={ev.type === 'alert' ? 'urgent' : ''}>
            {ev.type === 'alert' && `⚠ ${ev.message}`}
            {ev.type === 'spoken' && `Said: “${ev.text}”`}
            {ev.type === 'mode_change' && `Mode → ${ev.to}: ${ev.reason}`}
          </li>
        ))}
      </ul>
    </main>
  )
}
