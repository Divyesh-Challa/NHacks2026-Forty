// Keyboard simulator — drives the UI with no hardware and no backend.
//   ←/→ = LEFT/RIGHT, Space = SELECT, Backspace = BACK, hold H (2 s) = HELP, M = toggle split/scan
import type { Command } from './types'

const HELP_HOLD_MS = 2000

export function attachKeyboardSim(onCommand: (c: Command) => void, onToggleMode: () => void): () => void {
  let helpTimer: ReturnType<typeof setTimeout> | undefined

  const down = (e: KeyboardEvent) => {
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
    if (e.repeat) return
    switch (e.key) {
      case 'ArrowLeft':
        onCommand('LEFT')
        break
      case 'ArrowRight':
        onCommand('RIGHT')
        break
      case ' ':
        onCommand('SELECT')
        break
      case 'Backspace':
        onCommand('BACK')
        break
      case 'h':
      case 'H':
        helpTimer = setTimeout(() => onCommand('HELP'), HELP_HOLD_MS)
        break
      case 'm':
      case 'M':
        onToggleMode()
        break
      default:
        return
    }
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
