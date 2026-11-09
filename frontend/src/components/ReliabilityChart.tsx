// Per-signal reliability over time (0–100%), with the remap cutoff.
// One hue: eye movement (the signal that fades in the demo) is brand yellow, blink is neutral grey.
// Lines are direct-labelled and listed in a legend table with their latest value, so identity
// never rests on colour alone. Drawn at the container's real pixel width so text stays 12px.
// Styles: pages/caregiver.css (.cg-plot, .cg-legend).
import { useEffect, useRef, useState } from 'react'

export interface ReliabilityPoint {
  t: number
  signals: Record<string, number>
}

const SERIES = [
  { key: 'eog_h', label: 'Eye movement', short: 'Eye', color: '#ffd400' },
  { key: 'blink', label: 'Blink', short: 'Blink', color: '#b4b4b4' },
]
const TICKS = [0, 0.25, 0.5, 0.75, 1]
const LABEL_GAP = 14
const PAD = { top: 12, right: 52, bottom: 24, left: 40 }

/** End-of-line label y positions, nudged apart so overlapping lines don't stack their labels. */
function labelYs(ends: { key: string; y: number }[]): Record<string, number> {
  const sorted = [...ends].sort((a, b) => a.y - b.y)
  for (let i = 1; i < sorted.length; i++) {
    sorted[i].y = Math.max(sorted[i].y, sorted[i - 1].y + LABEL_GAP)
  }
  return Object.fromEntries(sorted.map((e) => [e.key, e.y]))
}

const pct = (r: number | undefined) => (r === undefined ? '—' : `${Math.round(r * 100)}%`)
const ago = (ms: number) => (ms < 90_000 ? `${Math.round(ms / 1000)} s ago` : `${Math.round(ms / 60_000)} min ago`)

export function ReliabilityChart({ points, cutoff }: { points: ReliabilityPoint[]; cutoff: number }) {
  const [hover, setHover] = useState<number | null>(null)
  const [w, setW] = useState(326)
  const box = useRef<HTMLDivElement>(null)

  const ready = points.length >= 2 // the plot box only exists once there is something to draw
  useEffect(() => {
    const el = box.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setW(Math.max(240, Math.round(e.contentRect.width))))
    ro.observe(el)
    return () => ro.disconnect()
  }, [ready])

  const cut = Math.round(cutoff * 100)
  if (!ready) {
    return (
      <div className="cg-empty" style={{ marginTop: 16 }}>
        <strong>Waiting for signal data…</strong>
        The chart fills in as soon as the signal service is running.
      </div>
    )
  }

  const H = w < 520 ? 200 : 220
  const PLOT_W = w - PAD.left - PAD.right
  const PLOT_H = H - PAD.top - PAD.bottom
  const y = (r: number) => PAD.top + (1 - r) * PLOT_H
  const t0 = points[0].t
  const span = Math.max(points[points.length - 1].t - t0, 1)
  const x = (t: number) => PAD.left + ((t - t0) / span) * PLOT_W
  const last = points[points.length - 1]
  const hovered = hover === null ? null : points[hover]
  const labelY = labelYs(
    SERIES.filter((s) => last.signals[s.key] !== undefined).map((s) => ({ key: s.key, y: y(last.signals[s.key]) + 4 })),
  )

  const onMove = (e: React.PointerEvent<SVGRectElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    const t = t0 + ((e.clientX - r.left) / r.width) * span
    let best = 0
    points.forEach((p, i) => {
      if (Math.abs(p.t - t) < Math.abs(points[best].t - t)) best = i
    })
    setHover(best)
  }

  return (
    <figure className="cg-card cg-chart" style={{ margin: '16px 0 0' }}>
      <div className="cg-chart-head">
        <h3 style={{ fontSize: 15, fontWeight: 600 }}>Signal reliability</h3>
        <span>Last {ago(span).replace(' ago', '')}</span>
      </div>
      <ul className="cg-legend">
        {SERIES.map((s) => {
          const v = last.signals[s.key]
          return (
            <li key={s.key}>
              <span className="sw" style={{ background: s.color }} />
              <span className="n">
                {s.label}
                {v !== undefined && v < cutoff && <small>Below the line</small>}
              </span>
              <span className="v">{pct(v)}</span>
            </li>
          )
        })}
      </ul>
      <div className="cg-plot" ref={box}>
        <svg width={w} height={H} viewBox={`0 0 ${w} ${H}`} role="img" aria-label="Signal reliability over time">
          {TICKS.map((r) => (
            <g key={r}>
              <line className={r === 0 ? 'base' : 'grid'} x1={PAD.left} x2={PAD.left + PLOT_W} y1={y(r)} y2={y(r)} />
              <text x={PAD.left - 8} y={y(r) + 4} textAnchor="end">{r * 100}%</text>
            </g>
          ))}
          <line className="cutoff" x1={PAD.left} x2={PAD.left + PLOT_W} y1={y(cutoff)} y2={y(cutoff)} />
          <text className="cut" x={PAD.left + 6} y={y(cutoff) + 15}>Switches control below {cut}%</text>
          <text x={PAD.left} y={H - 6}>{ago(span)}</text>
          <text x={PAD.left + PLOT_W} y={H - 6} textAnchor="end">now</text>

          {[...SERIES].reverse().map((s) => { // eye last, so the main series is drawn on top
            const pts = points.filter((p) => p.signals[s.key] !== undefined)
            if (!pts.length) return null
            const d = pts.map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(1)},${y(p.signals[s.key]).toFixed(1)}`).join('')
            const end = last.signals[s.key]
            return (
              <g key={s.key}>
                <path d={d} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
                {end !== undefined && (
                  <text className="direct" x={PAD.left + PLOT_W + 6} y={labelY[s.key]}>{s.short}</text>
                )}
              </g>
            )
          })}

          {hovered && (
            <g>
              <line className="crosshair" x1={x(hovered.t)} x2={x(hovered.t)} y1={PAD.top} y2={PAD.top + PLOT_H} />
              {SERIES.map((s) =>
                hovered.signals[s.key] === undefined ? null : (
                  <circle key={s.key} cx={x(hovered.t)} cy={y(hovered.signals[s.key])} r={4} fill={s.color} stroke="#15171a" strokeWidth={2} />
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
      </div>
      <div className="cg-tip" aria-live="off">
        {hovered
          ? `${new Date(hovered.t).toLocaleTimeString()} · ${SERIES.map((s) => `${s.label} ${pct(hovered.signals[s.key])}`).join(' · ')}`
          : 'Touch or hover the chart to read a moment.'}
      </div>
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
