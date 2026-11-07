// Shown on mode_change, e.g. "Eye movement is getting harder to read. Switching to jaw clench."
import { useEffect, useState } from 'react'
import type { ModeChangeEvent } from '../lib/types'

export function ModeBanner({ change }: { change: ModeChangeEvent | null }) {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if (!change) return
    setVisible(true)
    const t = setTimeout(() => setVisible(false), 6000)
    return () => clearTimeout(t)
  }, [change])

  if (!change || !visible) return null
  return (
    <div className="banner" role="status">
      Switching to {change.to} mode — {change.reason}
    </div>
  )
}
