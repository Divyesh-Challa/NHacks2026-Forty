// The backend still calls wheel mode "split" until its follow-up lands; read it as "wheel" here,
// once, so every page (patient, caregiver, demo) sees the new contract.
import type { ServerEvent } from './types'

const fix = (m: unknown) => (m === 'split' ? 'wheel' : m)

export function normalizeEvent(ev: Record<string, unknown>): ServerEvent {
  if (ev.type === 'reliability') return { ...ev, mode: fix(ev.mode) } as unknown as ServerEvent
  if (ev.type === 'mode_change') return { ...ev, from: fix(ev.from), to: fix(ev.to) } as unknown as ServerEvent
  return ev as unknown as ServerEvent
}
