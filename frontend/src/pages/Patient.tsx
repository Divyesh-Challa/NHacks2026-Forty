// Patient screen: boards -> phrase -> TTS. Works with keyboard sim alone; backend optional.
import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { LetterBoard } from '../components/LetterBoard'
import { SPELL_DELETE, SPELL_ITEMS, SPELL_SPACE, SPELL_SPEAK } from '../lib/spell'
import { ModeBanner } from '../components/ModeBanner'
import { PredictionStrip } from '../components/PredictionStrip'
import { ScanBoard } from '../components/ScanBoard'
import { SplitBoard } from '../components/SplitBoard'
import { getBoards, getConfig, predict } from '../lib/api'
import { attachKeyboardSim } from '../lib/keyboardSim'
import { speak } from '../lib/tts'
import type { Board, Command, Mode, ModeChangeEvent } from '../lib/types'
import { connect, type RelaySocket } from '../lib/ws'

// Used when the backend is down so the board still demos.
const OFFLINE_BOARDS: Board[] = [
  { id: 'needs', title: 'Needs', items: ['I need water', "I'm hungry", 'Bathroom', 'Reposition me', "I'm in pain"] },
  { id: 'yesno', title: 'Yes / No', items: ['Yes', 'No'] },
]
const SPELL_BOARD: Board = { id: '__spell', title: 'Spell', items: SPELL_ITEMS }
const SCAN_BACK = '← Back'
const SCAN_HELP = '⚠ HELP'
const PREDICTION_MARK = '★ '

const GESTURE_LABELS: Record<string, string> = {
  look_left: 'look left',
  look_right: 'look right',
  blink_double: 'double blink',
  jaw_clench: 'clench jaw',
  jaw_hold: 'hold jaw 2 s',
  brow_raise: 'raise eyebrows',
}

export default function Patient() {
  const { id = 'p1' } = useParams()
  const [boards, setBoards] = useState<Board[]>(OFFLINE_BOARDS)
  const [boardId, setBoardId] = useState<string | null>(null)
  const [mode, setMode] = useState<Mode>('split')
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [scanMs, setScanMs] = useState(1500)
  const [command, setCommand] = useState<{ command: Command; id: number } | null>(null)
  const [modeChange, setModeChange] = useState<ModeChangeEvent | null>(null)
  const [spoken, setSpoken] = useState<string[]>([])
  // Predictions remember which (patient, spoken) they answer; a mismatch means a request is in flight.
  const [prediction, setPrediction] = useState<{ id: string; spoken: string[]; phrases: string[] } | null>(null)
  const predictions = prediction?.phrases ?? []
  const predicting = !prediction || prediction.id !== id || prediction.spoken !== spoken
  const [spelled, setSpelled] = useState('')
  const [helpActive, setHelpActive] = useState(false)
  const [connected, setConnected] = useState(false)
  const sock = useRef<RelaySocket | null>(null)
  const seq = useRef(0)

  const help = useCallback(() => {
    setHelpActive(true)
    sock.current?.send({ type: 'alert', message: 'HELP', ts: Date.now() })
  }, [])

  const dispatch = useCallback(
    (c: Command) => {
      if (c === 'HELP') return help()
      if (c === 'BACK' && boardId) return setBoardId(null)
      setCommand({ command: c, id: ++seq.current })
    },
    [boardId, help],
  )
  const dispatchRef = useRef(dispatch)
  useEffect(() => {
    dispatchRef.current = dispatch
  }, [dispatch])

  useEffect(() => {
    getBoards(id).then(setBoards).catch(() => {})
    getConfig().then((c) => setScanMs(c.ui.scan_interval_ms)).catch(() => {})
  }, [id])

  // Refresh suggestions after every spoken message (and on load).
  useEffect(() => {
    let cancelled = false
    const done = (phrases: string[]) => !cancelled && setPrediction({ id, spoken, phrases })
    predict(id, [...spoken].reverse())
      .then((r) => done(r.phrases))
      .catch(() => done([]))
    return () => {
      cancelled = true
    }
  }, [id, spoken])

  useEffect(() => {
    const s = connect(
      `/ws/patient/${id}`,
      (ev) => {
        if (ev.type === 'command') dispatchRef.current(ev.command)
        else if (ev.type === 'reliability') {
          setMode(ev.mode)
          setMapping(ev.mapping as Record<string, string>)
        } else if (ev.type === 'mode_change') {
          setMode(ev.to)
          setModeChange(ev)
        } else if (ev.type === 'boards_updated') setBoards(ev.boards)
      },
      setConnected,
    )
    sock.current = s
    return () => s.close()
  }, [id])

  useEffect(
    () =>
      attachKeyboardSim(dispatch, () => {
        const next = mode === 'split' ? 'scan' : 'split'
        if (connected) sock.current?.send({ type: 'set_mode', mode: next })
        else {
          setModeChange({ type: 'mode_change', from: mode, to: next, reason: `Switching to ${next} mode.` })
          setMode(next)
        }
      }),
    [dispatch, mode, connected],
  )

  const allBoards = [...boards, SPELL_BOARD]
  const board = allBoards.find((b) => b.id === boardId)
  const topLevel = [...predictions.map((p) => PREDICTION_MARK + p), ...allBoards.map((b) => b.title)]
  const baseItems = board ? board.items : topLevel
  const items = mode === 'scan' ? [...baseItems, SCAN_BACK, SCAN_HELP] : baseItems

  const say = (text: string) => {
    // Confirmed selection — the only place TTS fires.
    speak(text)
    setSpoken((s) => [text, ...s].slice(0, 5))
    sock.current?.send({ type: 'spoken', text, ts: Date.now() })
  }

  const onSelect = (item: string) => {
    if (item === SCAN_HELP) return help()
    if (item === SCAN_BACK) return setBoardId(null)
    if (board?.id === SPELL_BOARD.id) {
      if (item === SPELL_SPEAK) {
        if (spelled.trim()) say(spelled.trim())
        setSpelled('')
        setBoardId(null)
      } else if (item === SPELL_DELETE) setSpelled((t) => t.slice(0, -1))
      else if (item === SPELL_SPACE) setSpelled((t) => t + ' ')
      else setSpelled((t) => t + item)
      return
    }
    if (!board) {
      if (item.startsWith(PREDICTION_MARK)) return say(item.slice(PREDICTION_MARK.length))
      setBoardId(allBoards.find((b) => b.title === item)?.id ?? null)
      return
    }
    say(item)
    setBoardId(null)
  }

  // Split mode shows LEFT/RIGHT on the halves themselves; the header lists the rest.
  const controls = [['Select', mapping.SELECT], ['HELP', mapping.HELP]]

  return (
    <main className="patient">
      <header>
        <span>{board ? board.title : 'Home'}</span>
        <span className="status">
          {controls
            .filter(([, g]) => g)
            .map(([label, g]) => `${label}: ${GESTURE_LABELS[g!] ?? g}`)
            .join(' · ')}
          {' · '}
          {mode} · {connected ? 'online' : 'offline'}
        </span>
      </header>
      <ModeBanner change={modeChange} />
      {!board && predicting && !predictions.length && <PredictionStrip phrases={[]} loading />}
      {board?.id === SPELL_BOARD.id && <LetterBoard text={spelled} />}
      {mode === 'split' ? (
        <SplitBoard
          items={items}
          command={command}
          onSelect={onSelect}
          leftHint={mapping.LEFT ? GESTURE_LABELS[mapping.LEFT] ?? mapping.LEFT : 'left arrow'}
          rightHint={mapping.RIGHT ? GESTURE_LABELS[mapping.RIGHT] ?? mapping.RIGHT : 'right arrow'}
        />
      ) : (
        <ScanBoard items={items} command={command} onSelect={onSelect} intervalMs={scanMs} />
      )}
      {spoken[0] && <footer>Said: “{spoken[0]}”</footer>}
      {helpActive && (
        <div className="help-overlay" onClick={() => setHelpActive(false)}>HELP sent to caregiver</div>
      )}
    </main>
  )
}
