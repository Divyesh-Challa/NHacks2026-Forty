// Shown on mode_change with the backend's plain-language reason,
// e.g. "Eye movement reliability fell below 60%. Switching to scan mode with double blink to select."
import { useEffect, useState } from 'react'
import type { ModeChangeEvent } from '../lib/types'

const SHOW_MS = 8000

export function ModeBanner({ change }: { change: ModeChangeEvent | null }) {
  const [hiddenFor, setHiddenFor] = useState<ModeChangeEvent | null>(null)

  useEffect(() => {
    if (!change) return
    const t = setTimeout(() => setHiddenFor(change), SHOW_MS)
    return () => clearTimeout(t)
  }, [change])

  if (!change || hiddenFor === change) return null
  return (
    <div className="mode-banner" role="status">
      <span className="mb-mark" aria-hidden="true" />
      <div className="mb-text">
        <strong>{change.to === 'scan' ? 'Switching to scan mode' : 'Back to wheel mode'}</strong>
        <span>{change.reason}</span>
      </div>
      <button type="button" className="mb-close" onClick={() => setHiddenFor(change)}>
        Dismiss
      </button>
    </div>
  )
}
