// Keyboard simulator — drives the UI with no hardware and no backend.
//   ←/→/↑/↓ = LEFT/RIGHT/UP/DOWN (the four looks), B = ACCEPT (double blink), Space = SELECT (double blink),
//   Backspace = BACK, hold H (2 s) = HELP, M = toggle wheel/scan, F = mouse-flick sim, A = audio aid,
//   1-9 = guided demo scenario, 0 = guide off
import type { Command } from './types'

const HELP_HOLD_MS = 2000

const KEYS: Record<string, Command> = {
  ArrowLeft: 'LEFT',
  ArrowRight: 'RIGHT',
  ArrowUp: 'UP',
  ArrowDown: 'DOWN',
  b: 'ACCEPT',
  ' ': 'SELECT',
  Backspace: 'BACK',
}

export function attachKeyboardSim(
  onCommand: (c: Command) => void,
  toggles: { mode(): void; flick(): void; aid(): void; demo(n: number): void },
): () => void {
  let helpTimer: ReturnType<typeof setTimeout> | undefined

  const down = (e: KeyboardEvent) => {
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
    if (e.repeat) return
    const key = e.key.length === 1 ? e.key.toLowerCase() : e.key
    if (KEYS[key]) onCommand(KEYS[key])
    else if (key === 'h') helpTimer = setTimeout(() => onCommand('HELP'), HELP_HOLD_MS)
    else if (key === 'm') toggles.mode()
    else if (key === 'f') toggles.flick()
    else if (key === 'a') toggles.aid()
    else if (/^[0-9]$/.test(key)) toggles.demo(Number(key))
    else return
    e.preventDefault()
  }
  const up = (e: KeyboardEvent) => {
    if (e.key === 'h' || e.key === 'H') clearTimeout(helpTimer)
  }

  window.addEventListener('keydown', down)
  window.addEventListener('keyup', up)
  return () => {
    window.removeEventListener('keydown', down)
    window.removeEventListener('keyup', up)
    clearTimeout(helpTimer)
  }
}
