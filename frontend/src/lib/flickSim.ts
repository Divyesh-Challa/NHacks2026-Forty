// Mouse-flick simulator: a quick cursor move away from the screen centre = one look, like a glance.
// EOG only sees jumps, never where the eyes point, so position, hover and clicks do nothing here.
// After a flick the cursor must come back near the centre before the next one (eyes returning).
import type { Dir } from './wheel.ts'

export class FlickDetector {
  private armed = false
  private readonly flickPx: number
  private readonly rearmPx: number

  constructor(opts: { flickPx: number; rearmPx: number }) {
    this.flickPx = opts.flickPx
    this.rearmPx = opts.rearmPx
  }

  // dx, dy: cursor offset from the viewport centre (screen y points down).
  move(dx: number, dy: number): Dir | null {
    const dist = Math.hypot(dx, dy)
    if (!this.armed) {
      if (dist <= this.rearmPx) this.armed = true
      return null
    }
    if (dist < this.flickPx) return null
    this.armed = false
    if (Math.abs(dx) > Math.abs(dy)) return dx > 0 ? 'right' : 'left'
    return dy > 0 ? 'down' : 'up'
  }
}
