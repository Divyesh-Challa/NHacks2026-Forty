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
    <div className="banner" role="status">
      {change.reason}
    </div>
  )
}
