// Patient screen: radial wheel → read-back → speech. Works with the keyboard sim alone; backend optional.
// All behaviour lives in lib/wheelMachine.ts; this page feeds it commands and ticks, then carries out
// the effects it returns (aid voice, real speech, learned words, HELP).
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { LetterBoard, LetterGrid } from '../components/LetterBoard'
import { ModeBanner } from '../components/ModeBanner'
import { RadialWheel } from '../components/RadialWheel'
import { getConfig } from '../lib/api'
import { allowed, DEMO_SCENARIOS } from '../lib/demoPath'
import { FlickDetector } from '../lib/flickSim'
import { attachKeyboardSim } from '../lib/keyboardSim'
import { pairedToken } from '../lib/pairing'
import { SPELL_ITEMS } from '../lib/spell'
import { aid, speak, unlock } from '../lib/tts'
import type { Command, Mode, ModeChangeEvent } from '../lib/types'
import { keyChain, view } from '../lib/wheel'
import type { Dir } from '../lib/wheel'
import { INITIAL, step, targets } from '../lib/wheelMachine'
import type { Action, Ctx, MachineState, Target } from '../lib/wheelMachine'
import { WHEEL } from '../lib/wheelTree'
import { learn, loadWords, saveWords, suggest } from '../lib/words'
import type { WordLink } from '../lib/words'
import { connect, type RelaySocket } from '../lib/ws'

const GESTURE_LABELS: Record<string, string> = {
  look_left: 'look left',
  look_right: 'look right',
  look_up: 'look up',
  look_down: 'look down',
  blink_double: 'double blink',
  brow_raise: 'raise eyebrows',
}
const LOOK_COMMANDS: Record<Dir, Command> = { up: 'UP', right: 'RIGHT', down: 'DOWN', left: 'LEFT' }

function readFlag(key: string, fallback: boolean): boolean {
  try {
    const v = localStorage.getItem(key)
    return v === null ? fallback : v === '1'
  } catch {
    return fallback
  }
}
function writeFlag(key: string, on: boolean): void {
  try {
    localStorage.setItem(key, on ? '1' : '0')
  } catch {
    // Blocked storage: the setting lasts for this session.
  }
}

export default function Patient() {
  const { id = 'p1' } = useParams()
  const [machine, setMachine] = useState<MachineState>(INITIAL)
  const [mode, setMode] = useState<Mode>('wheel')
  const [links, setLinks] = useState<WordLink[]>(() => loadWords(id))
  const [aidOn, setAidOn] = useState(() => readFlag('relay_aid', true))
  const [flickOn, setFlickOn] = useState(() => readFlag('relay_flick', false))
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [scanMs, setScanMs] = useState(1500)
  const [flickCfg, setFlickCfg] = useState({ flickPx: 160, rearmPx: 50 })
  const [modeChange, setModeChange] = useState<ModeChangeEvent | null>(null)
  const [spoken, setSpoken] = useState<string[]>([])
  const [helpActive, setHelpActive] = useState(false)
  const [connected, setConnected] = useState(false)
  const [tickEpoch, setTickEpoch] = useState(0)
  const [demo, setDemo] = useState<string | null>(null) // guided demo sentence (keys 1-9), see lib/demoPath.ts
  const sock = useRef<RelaySocket | null>(null)
  // The stage demo runs unpaired: with no token the WS simply connects without ?token=.
  const token = useMemo(() => pairedToken(id), [id])

  const ctx: Ctx = useMemo(
    () => ({ root: WHEEL, mode, suggestFor: (p) => suggest(links, keyChain(p), Date.now()) }),
    [mode, links],
  )

  // The socket, timers and key handlers outlive renders, so they read the latest values from here.
  const machineRef = useRef(machine)
  const live = useRef({ ctx, aidOn, links, demo })
  useEffect(() => {
    live.current = { ctx, aidOn, links, demo }
  })

  const run = useCallback(
    (action: Action) => {
      const { ctx, aidOn, links, demo } = live.current
      if (demo && action.type === 'command' && !allowed(action.command, machineRef.current, ctx, demo)) return
      const [next, effects] = step(machineRef.current, action, ctx)
      machineRef.current = next
      setMachine(next)
      // Anything but a tick restarts the scan clock, so the first highlight after a pick gets a full interval.
      if (action.type !== 'tick') setTickEpoch((n) => n + 1)
      let nextLinks = links
      for (const e of effects) {
        if (e.kind === 'aid') {
          if (aidOn || e.always) aid(e.text, e.always)
        } else if (e.kind === 'say') {
          // Confirmed sentence — the only place the real voice fires.
          speak(e.text)
          setSpoken((s) => [e.text, ...s].slice(0, 5))
          sock.current?.send({ type: 'spoken', text: e.text, path: e.path, ts: Date.now() })
        } else if (e.kind === 'learn') {
          nextLinks = learn(nextLinks, e.key, e.word, Date.now())
        } else {
          setHelpActive(true)
          sock.current?.send({ type: 'alert', message: 'HELP', ts: Date.now() })
        }
      }
      if (nextLinks !== links) {
        live.current.links = nextLinks
        setLinks(nextLinks)
        saveWords(id, nextLinks)
      }
    },
    [id],
  )

  useEffect(() => {
    getConfig()
      .then((c) => {
        setScanMs(c.ui.scan_interval_ms)
        setFlickCfg({ flickPx: c.ui.flick_px ?? 160, rearmPx: c.ui.flick_rearm_px ?? 50 })
      })
      .catch(() => {})
  }, [id])

  useEffect(() => {
    const s = connect(
      `/ws/patient/${id}${token ? `?token=${encodeURIComponent(token)}` : ''}`,
      (ev) => {
        if (ev.type === 'command') run({ type: 'command', command: ev.command })
        else if (ev.type === 'reliability') {
          setMode(ev.mode)
          setMapping(ev.mapping as Record<string, string>)
        } else if (ev.type === 'mode_change') {
          setMode(ev.to)
          setModeChange(ev)
        }
      },
      setConnected,
    )
    sock.current = s
    return () => s.close()
  }, [id, run, token])

  // Sound stays blocked until the first click or key press on this page (see tts.unlock).
  const [soundReady, setSoundReady] = useState(() => navigator.userActivation?.hasBeenActive ?? true)
  useEffect(() => {
    if (soundReady) return
    const ready = () => {
      unlock()
      setSoundReady(true)
    }
    window.addEventListener('pointerdown', ready, { once: true })
    window.addEventListener('keydown', ready, { once: true })
    return () => {
      window.removeEventListener('pointerdown', ready)
      window.removeEventListener('keydown', ready)
    }
  }, [soundReady])

  // A mode switch keeps the half-built message and restarts the scan at the first target.
  useEffect(() => {
    run({ type: 'mode' })
  }, [mode, run])

  const scanning = mode === 'scan' || machine.phase === 'spell'
  useEffect(() => {
    if (!scanning) return
    const t = setInterval(() => run({ type: 'tick' }), scanMs)
    return () => clearInterval(t)
  }, [scanning, scanMs, run, tickEpoch])

  useEffect(() => writeFlag('relay_aid', aidOn), [aidOn])
  useEffect(() => writeFlag('relay_flick', flickOn), [flickOn])

  useEffect(
    () =>
      attachKeyboardSim((command) => run({ type: 'command', command }), {
        mode: () => {
          const next: Mode = mode === 'wheel' ? 'scan' : 'wheel'
          if (connected) sock.current?.send({ type: 'set_mode', mode: next })
          else {
            setModeChange({ type: 'mode_change', from: mode, to: next, reason: `Switching to ${next} mode.` })
            setMode(next)
          }
        },
        flick: () => setFlickOn((on) => !on),
        aid: () => setAidOn((on) => !on),
        demo: (n) => {
          const next = DEMO_SCENARIOS[n - 1] ?? null // 0 = off
          live.current.demo = next
          setDemo(next)
          machineRef.current = INITIAL // each scenario starts from Home
          setMachine(INITIAL)
        },
      }),
    [mode, connected, run],
  )

  // Mouse-flick sim: a quick move away from the screen centre = one look.
  useEffect(() => {
    if (!flickOn) return
    const detector = new FlickDetector(flickCfg)
    const onMove = (e: PointerEvent) => {
      const dir = detector.move(e.clientX - window.innerWidth / 2, e.clientY - window.innerHeight / 2)
      if (dir) run({ type: 'command', command: LOOK_COMMANDS[dir] })
    }
    window.addEventListener('pointermove', onMove)
    return () => window.removeEventListener('pointermove', onMove)
  }, [flickOn, flickCfg, run])

  const v = view(WHEEL, machine.path)
  const last = machine.path.at(-1)
  const centreWord = v.picked === 'centre' ? last!.node.word : ctx.suggestFor(machine.path)
  const scanTargets = targets(machine, ctx)
  const highlight = mode === 'scan' && machine.phase === 'wheel' ? (scanTargets[machine.scanIndex] as Target) : null
  const extras = mode === 'scan' ? (scanTargets.filter((t) => t === 'finish' || t === 'help') as Target[]) : []
  const crumb = ['Home', ...machine.path.map((p) => p.node.word)].join(' › ')
  const controls = [
    ['Finish', mapping.SELECT],
    ['Accept', mapping.ACCEPT],
    ['HELP', mapping.HELP],
  ].filter(([, g]) => g)

  return (
    <main className="patient">
      <header>
        <span>{crumb}</span>
        <span className="status">
          {controls.map(([label, g]) => `${label}: ${GESTURE_LABELS[g!] ?? g}`).join(' · ')}
          {controls.length ? ' · ' : ''}
          {demo ? `demo: ${demo} · ` : ''}
          {mode} · aid {aidOn ? 'on' : 'off'} · {flickOn ? 'mouse flick on · ' : ''}
          {connected ? 'online' : 'offline'} · {token ? 'Paired' : <>Not paired · open <Link to="/pair">/pair</Link></>}
        </span>
      </header>
      {!soundReady && (
        <div role="status" style={{ background: '#b45309', color: '#fff', padding: '8px 16px', textAlign: 'center' }}>
          Sound is off. Click anywhere or press a key once to turn it on.
        </div>
      )}
      <ModeBanner change={modeChange} />
      {machine.phase === 'spell' ? (
        <>
          <LetterBoard text={machine.spelled} />
          <LetterGrid items={SPELL_ITEMS} active={machine.scanIndex} />
        </>
      ) : (
        <RadialWheel view={v} suggestion={centreWord} highlight={highlight} extras={extras} intervalMs={scanMs} />
      )}
      {machine.phase === 'readback' && machine.readback && (
        <div className="readback" role="dialog" aria-live="assertive">
          <div className="sentence">
            {machine.readback.kind === 'word' ? `“${machine.readback.text}”?` : machine.readback.text}
          </div>
          {mode === 'scan' ? (
            <div className="choices">
              {[machine.readback.kind === 'help' ? '🚨 Send HELP' : '🔊 Speak', '✕ Cancel'].map((label, i) => (
                <div key={label} className={`item${machine.scanIndex === i ? ' active' : ''}`}>
                  {label}
                </div>
              ))}
            </div>
          ) : (
            <div className="hint">
              {machine.readback.kind === 'word' ? 'To save this word' : machine.readback.kind === 'help' ? 'To send HELP' : 'To speak'}: {GESTURE_LABELS[mapping.SELECT] ?? 'select'} · look to cancel
            </div>
          )}
        </div>
      )}
      {spoken[0] && <footer>Said: “{spoken[0]}”</footer>}
      {helpActive && (
        <div className="help-overlay" onClick={() => setHelpActive(false)}>
          HELP sent to caregiver
        </div>
      )}
    </main>
  )
}
