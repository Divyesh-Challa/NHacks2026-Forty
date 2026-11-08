// Per-signal reliability over time (0–100%), with the 60% remap cutoff.
// Colors: validated categorical slots 1–3 (dark) against the panel surface; lines are also
// direct-labeled and listed in the legend, so identity never rests on color alone.
import { useState } from 'react'

export interface ReliabilityPoint {
  t: number
  signals: Record<string, number>
}

const SERIES = [
  { key: 'eog_h', label: 'Eye movement', short: 'Eye', color: '#3987e5' },
  { key: 'blink', label: 'Blink', short: 'Blink', color: '#d95926' },
]
const LABEL_GAP = 12

/** End-of-line label y positions, nudged apart so overlapping lines don't stack their labels. */
function labelYs(ends: { key: string; y: number }[]): Record<string, number> {
  const sorted = [...ends].sort((a, b) => a.y - b.y)
  for (let i = 1; i < sorted.length; i++) {
    sorted[i].y = Math.max(sorted[i].y, sorted[i - 1].y + LABEL_GAP)
  }
  return Object.fromEntries(sorted.map((e) => [e.key, e.y]))
}
const W = 340
const H = 180
const PAD = { top: 12, right: 70, bottom: 22, left: 34 }
const PLOT_W = W - PAD.left - PAD.right
const PLOT_H = H - PAD.top - PAD.bottom

const y = (r: number) => PAD.top + (1 - r) * PLOT_H
const pct = (r: number | undefined) => (r === undefined ? '—' : `${Math.round(r * 100)}%`)

export function ReliabilityChart({ points, cutoff }: { points: ReliabilityPoint[]; cutoff: number }) {
  const [hover, setHover] = useState<number | null>(null)
  if (points.length < 2) return <p className="muted">Waiting for signal data…</p>

  const t0 = points[0].t
  const span = Math.max(points[points.length - 1].t - t0, 1)
  const x = (t: number) => PAD.left + ((t - t0) / span) * PLOT_W
  const last = points[points.length - 1]
  const hovered = hover === null ? null : points[hover]
  const labelY = labelYs(
    SERIES.filter((s) => last.signals[s.key] !== undefined).map((s) => ({ key: s.key, y: y(last.signals[s.key]) + 4 })),
  )

  const onMove = (e: React.PointerEvent<SVGRectElement>) => {
    const box = e.currentTarget.getBoundingClientRect()
    const t = t0 + ((e.clientX - box.left) / box.width) * span
    let best = 0
    points.forEach((p, i) => {
      if (Math.abs(p.t - t) < Math.abs(points[best].t - t)) best = i
    })
    setHover(best)
  }

  return (
    <figure className="chart">
      <ul className="legend">
        {SERIES.map((s) => (
          <li key={s.key}>
            <span className="swatch" style={{ background: s.color }} />
            {s.label}
          </li>
        ))}
      </ul>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Signal reliability over time">
        {[0, 0.5, 1].map((r) => (
          <g key={r}>
            <line className="grid" x1={PAD.left} x2={PAD.left + PLOT_W} y1={y(r)} y2={y(r)} />
            <text className="axis" x={PAD.left - 6} y={y(r) + 4} textAnchor="end">{r * 100}%</text>
          </g>
        ))}
        <line className="cutoff" x1={PAD.left} x2={PAD.left + PLOT_W} y1={y(cutoff)} y2={y(cutoff)} />
        <text className="axis" x={PAD.left + 4} y={y(cutoff) - 4}>switch below {cutoff * 100}%</text>
        <text className="axis" x={PAD.left} y={H - 6}>{Math.round(span / 1000)} s ago</text>
        <text className="axis" x={PAD.left + PLOT_W} y={H - 6} textAnchor="end">now</text>

        {SERIES.map((s) => {
          const pts = points.filter((p) => p.signals[s.key] !== undefined)
          if (!pts.length) return null
          const d = pts.map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(1)},${y(p.signals[s.key]).toFixed(1)}`).join('')
          const end = last.signals[s.key]
          return (
            <g key={s.key}>
              <path d={d} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
              {end !== undefined && (
                <text className="direct-label" x={PAD.left + PLOT_W + 6} y={labelY[s.key]}>
                  {s.short} {pct(end)}
                </text>
              )}
            </g>
          )
        })}

        {hovered && (
          <g>
            <line className="crosshair" x1={x(hovered.t)} x2={x(hovered.t)} y1={PAD.top} y2={PAD.top + PLOT_H} />
            {SERIES.map((s) =>
              hovered.signals[s.key] === undefined ? null : (
                <circle key={s.key} cx={x(hovered.t)} cy={y(hovered.signals[s.key])} r={4} fill={s.color} stroke="#1a1f27" strokeWidth={2} />
              ),
            )}
          </g>
        )}
        <rect
          x={PAD.left}
          y={PAD.top}
          width={PLOT_W}
          height={PLOT_H}
          fill="transparent"
          onPointerMove={onMove}
          onPointerLeave={() => setHover(null)}
        />
      </svg>
      {hovered && (
        <div className="tooltip">
          {new Date(hovered.t).toLocaleTimeString()} ·{' '}
          {SERIES.map((s) => `${s.label} ${pct(hovered.signals[s.key])}`).join(' · ')}
        </div>
      )}
      <table className="sr-table">
        <caption>Latest reliability</caption>
        <tbody>
          {SERIES.map((s) => (
            <tr key={s.key}>
              <th scope="row">{s.label}</th>
              <td>{pct(last.signals[s.key])}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  )
}
