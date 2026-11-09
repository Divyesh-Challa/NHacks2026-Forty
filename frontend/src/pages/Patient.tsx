// Patient screen: radial wheel → read-back → speech. Works with the keyboard sim alone; backend optional.
// All behaviour lives in lib/wheelMachine.ts; this page feeds it commands and ticks, then carries out
// the effects it returns (aid voice, real speech, learned words, HELP).
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { LetterBoard, LetterGrid } from '../components/LetterBoard'
import { ModeBanner } from '../components/ModeBanner'
import { RadialWheel, ScanTimer } from '../components/RadialWheel'
import { getConfig } from '../lib/api'
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
import './patient.css'

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
  // Recorded at send time: the socket drops alerts while it is not open, so a later reconnect must not rewrite it.
  const [helpActive, setHelpActive] = useState<'sent' | 'unsent' | null>(null)
  const [connected, setConnected] = useState(false)
  const [tickEpoch, setTickEpoch] = useState(0)
  const sock = useRef<RelaySocket | null>(null)
  // The stage demo runs unpaired: with no token the WS simply connects without ?token=.
  const token = useMemo(() => pairedToken(id), [id])

  const ctx: Ctx = useMemo(
    () => ({ root: WHEEL, mode, suggestFor: (p) => suggest(links, keyChain(p), Date.now()) }),
    [mode, links],
  )

  // The socket, timers and key handlers outlive renders, so they read the latest values from here.
  const machineRef = useRef(machine)
  const live = useRef({ ctx, aidOn, links })
  useEffect(() => {
    live.current = { ctx, aidOn, links }
  })

  const run = useCallback(
    (action: Action) => {
      const { ctx, aidOn, links } = live.current
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
          const delivered = sock.current?.send({ type: 'alert', message: 'HELP', ts: Date.now() }) ?? false
          setHelpActive(delivered ? 'sent' : 'unsent')
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
  const spelling = machine.phase === 'spell'
  const title = spelling ? 'Spell a word' : (last?.node.word ?? 'Home')
  const crumb = spelling
    ? 'Pick letters, then Speak to finish'
    : machine.path.length
      ? ['Home', ...machine.path.map((p) => p.node.word)].join(' › ')
      : mode === 'scan'
        ? 'Select when the option you want is lit'
        : 'Look up, right, down or left to choose'
  const selectLabel = mode === 'scan' || spelling ? 'Select' : 'Finish'
  // Which gesture does what. Without a live mapping (keyboard sim, backend offline) show the keys instead.
  const mapped = [
    [selectLabel, mapping.SELECT],
    ['Accept', mapping.ACCEPT],
    ['HELP', mapping.HELP],
  ].filter(([, g]) => g)
  const controls = mapped.length
    ? mapped.map(([label, g]) => [label, GESTURE_LABELS[g!] ?? g!])
    : [
        [selectLabel, 'Space'],
        ['Accept', 'B'],
        ['HELP', 'hold H'],
      ]
  const selectHint = GESTURE_LABELS[mapping.SELECT] ?? 'Space'
  // The backend does not map ACCEPT today: only name a control that exists. Keyboard sim (no mapping at all) has B.
  const acceptHint = mapping.ACCEPT ? (GESTURE_LABELS[mapping.ACCEPT] ?? mapping.ACCEPT) : mapped.length === 0 ? 'B' : null
  const rb = machine.readback

  return (
    <main className="patient">
      <header className="pt-head">
        <div className="pt-brand">
          <span className="pt-mark" aria-hidden="true">R</span>
          <span className="pt-name">Relay</span>
        </div>
        <div className="pt-title">
          <h1>{title}</h1>
          <p>{crumb}</p>
        </div>
        <ul className="pt-controls" aria-label="Controls">
          {controls.map(([label, g]) => (
            <li key={label}>
              <span className="k">{label}</span>
              <span className="v">{g}</span>
            </li>
          ))}
        </ul>
        <div className="pt-status">
          <span className={`pt-live ${connected ? 'on' : 'off'}`}>
            <span className="dot" aria-hidden="true" />
            {connected ? 'Online' : 'Offline'} · {mode === 'wheel' ? 'Wheel' : 'Scan'} mode
          </span>
          <span className="pt-sub">
            {token ? 'Paired' : <>Not paired · <Link to="/pair">pair this device</Link></>} · Voice aid {aidOn ? 'on' : 'off'}
            {flickOn ? ' · Mouse flick on' : ''}
          </span>
        </div>
      </header>
      {!soundReady && (
        <div className="pt-notice warn" role="status">
          Sound is off. Click anywhere or press a key once to turn it on.
        </div>
      )}
      {!connected && (
        <div className="pt-notice late" role="status">
          Not connected to Relay. The keyboard still works, but signals will not arrive and HELP alerts can't be sent while offline.
        </div>
      )}
      <ModeBanner change={modeChange} />
      {spelling ? (
        <div className="spell">
          <LetterBoard text={machine.spelled} />
          <LetterGrid items={SPELL_ITEMS} active={machine.scanIndex} intervalMs={scanMs} epoch={tickEpoch} />
        </div>
      ) : (
        <RadialWheel view={v} suggestion={centreWord} highlight={highlight} extras={extras} intervalMs={scanMs} epoch={tickEpoch} acceptHint={acceptHint} />
      )}
      {machine.phase === 'readback' && rb && (
        <div className="readback" role="dialog" aria-live="assertive" aria-label="Confirm">
          <div className="rb-ask">{rb.kind === 'help' ? 'Send an alert?' : rb.kind === 'word' ? 'Save this word?' : 'Speak this aloud?'}</div>
          <div className="sentence">{rb.kind === 'word' ? `“${rb.text}”` : rb.text}</div>
          {mode === 'scan' ? (
            <div className="choices">
              {[rb.kind === 'help' ? 'Send HELP' : rb.kind === 'word' ? 'Save word' : 'Speak', 'Cancel'].map((label, i) => (
                <div key={label} className={`choice${i === 0 ? ' go' : ''}${rb.kind === 'help' && i === 0 ? ' help' : ''}${machine.scanIndex === i ? ' active' : ''}`}>
                  {label}
                  {machine.scanIndex === i && <ScanTimer ms={scanMs} epoch={tickEpoch} />}
                </div>
              ))}
            </div>
          ) : (
            <div className="hint">
              <span className="pt-keys">
                <kbd>{selectHint}</kbd> {rb.kind === 'word' ? 'to save this word' : rb.kind === 'help' ? 'to send HELP' : 'to speak'}
              </span>
              <span className="pt-keys">
                <kbd>look any way</kbd> to cancel
              </span>
            </div>
          )}
        </div>
      )}
      <footer className="pt-said" aria-live="polite">
        <span className="k">Said</span>
        {spoken[0] ? <q>{spoken[0]}</q> : <span className="none">Spoken phrases appear here</span>}
      </footer>
      {helpActive && (
        <div className={`help-overlay${helpActive === 'unsent' ? ' unsent' : ''}`} role="alertdialog" aria-label="HELP" onClick={() => setHelpActive(null)}>
          <span className="ring" aria-hidden="true" />
          <div className="big">{helpActive === 'sent' ? 'HELP sent' : 'HELP not sent'}</div>
          <div className="sub">
            {helpActive === 'sent' ? "Your caregiver's phone will alert if it's connected." : 'Relay was offline, so no one was alerted. Call out or use the call bell.'}
          </div>
          <div className="dismiss">Click anywhere to dismiss</div>
        </div>
      )}
    </main>
  )
}

