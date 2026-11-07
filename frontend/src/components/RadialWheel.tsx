// The radial wheel: four fixed directions plus the centre suggestion. Presentational only —
// navigation lives in lib/wheel.ts and lib/wheelMachine.ts.
import type { Dir, WheelView } from '../lib/wheel'
import { DIRS } from '../lib/wheel'
import type { Target } from '../lib/wheelMachine'

const ARROWS: Record<Dir, string> = { up: '↑', right: '→', down: '↓', left: '←' }
const EXTRA_LABELS: Partial<Record<Target, string>> = { finish: '✓ Finish', help: '⚠ HELP' }

function Timer({ on, ms }: { on: boolean; ms: number }) {
  return on ? <span className="scan-timer" style={{ animationDuration: `${ms}ms` }} /> : null
}

export function RadialWheel({
  view,
  suggestion,
  highlight,
  extras,
  intervalMs,
}: {
  view: WheelView
  suggestion: string | null
  highlight: Target | null // scan target; null in wheel mode
  extras: Target[] // 'finish' / 'help' in scan mode, shown under the wheel
  intervalMs: number
}) {
  return (
    <div className="wheel-wrap">
      <div className="wheel">
        {DIRS.map((d) => {
          const node = view.slots[d]
          const cls = [
            'item slot',
            d,
            !node && 'empty',
            view.kept === d && 'kept',
            view.picked === d && 'picked',
            highlight === d && 'active',
          ]
          return (
            <div key={d} className={cls.filter(Boolean).join(' ')}>
              <span className="arrow">{ARROWS[d]}</span>
              <span className="word">{node?.word ?? ''}</span>
              {view.kept === d && <span className="back-tag">back</span>}
              <Timer on={highlight === d} ms={intervalMs} />
            </div>
          )
        })}
        <div
          className={['item slot centre', !suggestion && 'empty', view.picked === 'centre' && 'picked', highlight === 'centre' && 'active']
            .filter(Boolean)
            .join(' ')}
        >
          {suggestion && <span className="arrow">suggested · double blink</span>}
          <span className="word">{suggestion ?? ''}</span>
          <Timer on={highlight === 'centre'} ms={intervalMs} />
        </div>
      </div>
      {extras.length > 0 && (
        <div className="wheel-extras">
          {extras.map((t) => (
            <div key={t} className={`item${t === 'help' ? ' help' : ''}${highlight === t ? ' active' : ''}`}>
              {EXTRA_LABELS[t] ?? t}
              <Timer on={highlight === t} ms={intervalMs} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
