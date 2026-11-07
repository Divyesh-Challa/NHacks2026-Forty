// Patient screen: boards -> phrase -> TTS. Works with keyboard sim alone; backend optional.
// Owner: Role C.
import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ModeBanner } from '../components/ModeBanner'
import { PredictionStrip } from '../components/PredictionStrip'
import { ScanBoard } from '../components/ScanBoard'
import { SplitBoard } from '../components/SplitBoard'
import { getBoards, getConfig } from '../lib/api'
import { attachKeyboardSim } from '../lib/keyboardSim'
import { speak } from '../lib/tts'
import type { Board, Command, Mode, ModeChangeEvent } from '../lib/types'
import { connect, type RelaySocket } from '../lib/ws'

// Used when the backend is down so the board still demos.
const OFFLINE_BOARDS: Board[] = [
  { id: 'needs', title: 'Needs', items: ['I need water', "I'm hungry", 'Bathroom', 'Reposition me', "I'm in pain"] },
  { id: 'yesno', title: 'Yes / No', items: ['Yes', 'No'] },
]
const SCAN_BACK = '← Back'
const SCAN_HELP = '⚠ HELP'

export default function Patient() {
  const { id = 'p1' } = useParams()
  const [boards, setBoards] = useState<Board[]>(OFFLINE_BOARDS)
  const [boardId, setBoardId] = useState<string | null>(null)
  const [mode, setMode] = useState<Mode>('split')
  const [scanMs, setScanMs] = useState(1500)
  const [command, setCommand] = useState<{ command: Command; id: number } | null>(null)
  const [modeChange, setModeChange] = useState<ModeChangeEvent | null>(null)
  const [spoken, setSpoken] = useState<string[]>([])
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

  useEffect(() => {
    const s = connect(
      `/ws/patient/${id}`,
      (ev) => {
        if (ev.type === 'command') dispatchRef.current(ev.command)
        else if (ev.type === 'reliability') setMode(ev.mode)
        else if (ev.type === 'mode_change') {
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
          setModeChange({ type: 'mode_change', from: mode, to: next, reason: 'manual toggle' })
          setMode(next)
        }
      }),
    [dispatch, mode, connected],
  )

  const board = boards.find((b) => b.id === boardId)
  const baseItems = board ? board.items : boards.map((b) => b.title)
  const items = mode === 'scan' ? [...baseItems, SCAN_BACK, SCAN_HELP] : baseItems

  const onSelect = (item: string) => {
    if (item === SCAN_HELP) return help()
    if (item === SCAN_BACK) return setBoardId(null)
    if (!board) {
      setBoardId(boards.find((b) => b.title === item)?.id ?? null)
      return
    }
    // Confirmed selection — the only place TTS fires.
    speak(item)
    setSpoken((s) => [item, ...s].slice(0, 5))
    sock.current?.send({ type: 'spoken', text: item, ts: Date.now() })
    setBoardId(null)
  }

  return (
    <main className="patient">
      <header>
        <span>{board ? board.title : 'Boards'}</span>
        <span className="status">{mode} · {connected ? 'online' : 'offline'}</span>
      </header>
      <ModeBanner change={modeChange} />
      <PredictionStrip phrases={[]} />
      {mode === 'split' ? (
        <SplitBoard items={items} command={command} onSelect={onSelect} />
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
