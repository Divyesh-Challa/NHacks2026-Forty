// The radial wheel: four fixed directions plus the centre suggestion. Presentational only —
// navigation lives in lib/wheel.ts and lib/wheelMachine.ts.
import type { Dir, WheelView } from '../lib/wheel'
import { DIRS } from '../lib/wheel'
import type { Target } from '../lib/wheelMachine'

const HINTS: Record<Dir, string> = { up: 'look up', right: 'look right', down: 'look down', left: 'look left' }
const ROTATE: Record<Dir, number> = { up: 0, right: 90, down: 180, left: 270 }
const EXTRA_LABELS: Partial<Record<Target, string>> = { finish: 'Finish', help: 'HELP' }

function Arrow({ dir }: { dir: Dir }) {
  return (
    <svg className="arrow" viewBox="0 0 24 24" width="28" height="28" aria-hidden="true" style={{ transform: `rotate(${ROTATE[dir]}deg)` }}>
      <path d="M12 20V5M5.5 11.5 12 5l6.5 6.5" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// The scan clock for the highlighted item. Remounts on every step (and on every non-tick action,
// which restarts the clock) so the bar always shows the time left on the current highlight.
export function ScanTimer({ ms, epoch }: { ms: number; epoch: number }) {
  return <span key={epoch} className="scan-timer" aria-hidden="true" style={{ animationDuration: `${ms}ms` }} />
}

export function RadialWheel({
  view,
  suggestion,
  highlight,
  extras,
  intervalMs,
  epoch,
  acceptHint,
}: {
  view: WheelView
  suggestion: string | null
  highlight: Target | null // scan target; null in wheel mode
  extras: Target[] // 'finish' / 'help' in scan mode, shown under the wheel
  intervalMs: number
  epoch: number // changes whenever the scan clock restarts
  acceptHint: string // the gesture that takes the suggestion
}) {
  const scanning = highlight !== null || extras.length > 0
  return (
    <div className="wheel-wrap">
      <div className="wheel">
        {DIRS.map((d) => {
          const node = view.slots[d]
          const cls = [
            'slot',
            d,
            !node && 'empty',
            view.kept === d && 'kept',
            view.picked === d && 'picked',
            highlight === d && 'active',
          ]
          return (
            <div key={d} className={cls.filter(Boolean).join(' ')}>
              <span className="cue">
                <Arrow dir={d} />
                {!scanning && node && <span className="hint">{view.kept === d ? `${HINTS[d]} to go back` : HINTS[d]}</span>}
              </span>
              <span className="word">{node?.word ?? ''}</span>
              {view.kept === d && scanning && <span className="back-tag">Back</span>}
              {highlight === d && <ScanTimer ms={intervalMs} epoch={epoch} />}
            </div>
          )
        })}
        <div
          className={['slot centre', !suggestion && 'empty', view.picked === 'centre' && 'picked', highlight === 'centre' && 'active']
            .filter(Boolean)
            .join(' ')}
        >
          {suggestion ? (
            <span className="cue">
              <span className="tag">Suggested</span>
              {!scanning && <span className="hint">{acceptHint} to accept</span>}
            </span>
          ) : (
            !scanning && (
              <span className="cue">
                <span className="hint">Words you spell appear here</span>
              </span>
            )
          )}
          <span className="word">{suggestion ?? ''}</span>
          {highlight === 'centre' && <ScanTimer ms={intervalMs} epoch={epoch} />}
        </div>
      </div>
      {extras.length > 0 && (
        <div className="wheel-extras">
          {extras.map((t) => (
            <div key={t} className={`extra${t === 'help' ? ' help' : ''}${highlight === t ? ' active' : ''}`}>
              {EXTRA_LABELS[t] ?? t}
              {highlight === t && <ScanTimer ms={intervalMs} epoch={epoch} />}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
