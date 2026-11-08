// Cue-driven calibration screen: a dot shows where to look, a tone and a voice say what to do.
// The recorder (signal/calibration.py --cue) decides the timing and labels the samples at the same
// instant it sends each cue, so what is on screen is exactly what the data is labelled with.
// The Start click is also the user gesture browsers need before they allow sound.
import { useEffect, useRef, useState } from 'react'
import './calibrate.css'

type Msg =
  | { type: 'hello' }
  | { type: 'ready'; seconds: number }
  | { type: 'intro'; seconds: number }
  | { type: 'cue'; gesture: string; seconds: number; hold_s: number; index: number; total: number; next: string | null }
  | { type: 'rest'; seconds: number; next: string | null }
  | { type: 'seen'; text: string } // live test only: what Relay just detected
  | { type: 'done' }

type Phase = 'offline' | 'idle' | 'run' | 'done'

const CENTRE: [number, number] = [50, 50]
const SPOT: Record<string, [number, number]> = {
  look_left: [8, 50],
  look_right: [92, 50],
  look_up: [50, 10],
  look_down: [50, 90],
}
const WORDS: Record<string, string> = {
  look_left: 'Look left',
  look_right: 'Look right',
  look_up: 'Look up',
  look_down: 'Look down',
  blink_double: 'Blink twice',
}

const sound = { muted: false, ctx: undefined as AudioContext | undefined }

function beep(hz: number, secs = 0.12): void {
  if (sound.muted) return
  try {
    sound.ctx ??= new AudioContext()
    const ctx = sound.ctx
    void ctx.resume()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.frequency.value = hz
    gain.gain.value = 0.15
    osc.connect(gain).connect(ctx.destination)
    osc.start()
    osc.stop(ctx.currentTime + secs)
  } catch {
    // No Web Audio: the voice (if any) still plays.
  }
}

function say(text: string): void {
  if (sound.muted || !('speechSynthesis' in window)) return
  window.speechSynthesis.cancel()
  window.speechSynthesis.speak(new SpeechSynthesisUtterance(text))
}

export default function Calibrate() {
  const [phase, setPhase] = useState<Phase>('offline')
  const [text, setText] = useState('')
  const [sub, setSub] = useState('')
  const [pos, setPos] = useState<[number, number]>(CENTRE)
  const [pulse, setPulse] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const [tick, setTick] = useState(0) // restarts the countdown bar on every message
  const [muted, setMuted] = useState(false)
  const [seen, setSeen] = useState('')
  const sock = useRef<WebSocket | null>(null)

  useEffect(() => {
    sound.muted = muted
    if (muted && 'speechSynthesis' in window) window.speechSynthesis.cancel()
  }, [muted])

  useEffect(() => {
    let closed = false
    let retry: ReturnType<typeof setTimeout> | undefined
    let back: ReturnType<typeof setTimeout> | undefined

    const show = (t: string, s: string, secs: number, p: [number, number] = CENTRE, pul = false) => {
      setText(t)
      setSub(s)
      setSeconds(secs)
      setPos(p)
      setPulse(pul)
      setTick((n) => n + 1)
    }

    const handle = (m: Msg) => {
      clearTimeout(back)
      if (m.type === 'seen') {
        setSeen(m.text)
        return
      }
      if (m.type === 'cue' || m.type === 'rest') setSeen('')
      if (m.type === 'ready') {
        setPhase('run')
        show('Get ready', 'Look at the dot in the centre', m.seconds)
        say('Get ready. Look at the dot in the centre.')
      } else if (m.type === 'intro') {
        show('Relax', 'Keep your eyes on the centre dot', m.seconds)
        say('Relax. Keep your eyes on the centre dot.')
      } else if (m.type === 'cue') {
        const spot = SPOT[m.gesture]
        const next = m.next ? ` · next: ${(WORDS[m.next] ?? m.next).toLowerCase()}` : ''
        show((WORDS[m.gesture] ?? m.gesture).toUpperCase(), `${m.index} of ${m.total}${next}`, m.seconds, spot ?? CENTRE, !spot)
        beep(880)
        say(WORDS[m.gesture] ?? m.gesture)
        if (spot && m.hold_s > 0) {
          back = setTimeout(() => {
            setPos(CENTRE)
            beep(440, 0.06)
          }, m.hold_s * 1000)
        }
      } else if (m.type === 'rest') {
        const next = m.next ? `Next: ${(WORDS[m.next] ?? m.next).toLowerCase()}` : ''
        show('Centre', next, m.seconds)
      } else if (m.type === 'done') {
        setPhase('done')
        setPos(CENTRE)
        setPulse(false)
        say('Calibration finished.')
      }
    }

    const open = () => {
      const ws = new WebSocket(`ws://${window.location.hostname}:8765`)
      sock.current = ws
      ws.onopen = () => setPhase((p) => (p === 'run' || p === 'done' ? p : 'idle'))
      ws.onclose = () => {
        setPhase((p) => (p === 'done' ? p : 'offline'))
        if (!closed) retry = setTimeout(open, 1500)
      }
      ws.onmessage = (e) => {
        try {
          handle(JSON.parse(e.data as string) as Msg)
        } catch {
          // Ignore a malformed message rather than breaking the run.
        }
      }
    }
    open()

    return () => {
      closed = true
      clearTimeout(retry)
      clearTimeout(back)
      sock.current?.close()
      if ('speechSynthesis' in window) window.speechSynthesis.cancel()
    }
  }, [])

  const start = () => {
    beep(660, 0.08) // creates the audio context inside the click, which unlocks sound
    if ('speechSynthesis' in window) window.speechSynthesis.speak(new SpeechSynthesisUtterance(''))
    sock.current?.send(JSON.stringify({ type: 'start' }))
  }

  return (
    <main className="cal">
      <header>
        <span>{phase === 'offline' ? 'Waiting for the calibration tool…' : 'Relay calibration'}</span>
        <button onClick={() => setMuted((m) => !m)} aria-pressed={muted}>
          {muted ? '🔇 Sound off' : '🔊 Sound on'}
        </button>
      </header>
      <div className="dot" data-pulse={pulse} style={{ left: `${pos[0]}%`, top: `${pos[1]}%` }} />
      <section className="msg" role="status" aria-live="polite">
        {phase === 'offline' && (
          <>
            <h1>Not connected</h1>
            <p>
              Run <code>make calibrate-cue PORT=/dev/cu.usbmodem101</code> (or the live test). This page connects by itself.
            </p>
          </>
        )}
        {phase === 'idle' && (
          <>
            <h1>Ready</h1>
            <p>Electrodes on, sit still, and keep your head still. Follow the dot with your eyes only.</p>
            <button className="start" onClick={start}>
              Start
            </button>
          </>
        )}
        {phase === 'run' && (
          <>
            <h1>{text}</h1>
            <p>{sub}</p>
            {seen && <p className="seen">Detected: {seen}</p>}
          </>
        )}
        {phase === 'done' && (
          <>
            <h1>Done</h1>
            <p>Check the terminal for the results.</p>
          </>
        )}
      </section>
      {phase === 'run' && seconds > 0 && <div key={tick} className="bar" style={{ animationDuration: `${seconds}s` }} />}
    </main>
  )
}
