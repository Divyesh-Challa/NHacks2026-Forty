// HELP alert sound + vibration for the caregiver phone.
// Mobile browsers keep audio locked until a tap, so call unlockAlerts() from a click handler
// (login, or the "Enable alert sound" button) before an alert can be heard.
let ctx: AudioContext | null = null

export function unlockAlerts(): void {
  ctx ??= new AudioContext()
  if (ctx.state === 'suspended') void ctx.resume()
}

export function alertsUnlocked(): boolean {
  return ctx?.state === 'running'
}

export function playHelpAlert(): void {
  navigator.vibrate?.([400, 150, 400, 150, 400])
  if (!ctx) return
  const start = ctx.currentTime
  for (const [i, f] of [880, 660, 880, 660, 880].entries()) {
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    gain.gain.value = 0.4
    osc.frequency.value = f
    osc.connect(gain).connect(ctx.destination)
    osc.start(start + i * 0.25)
    osc.stop(start + i * 0.25 + 0.2)
  }
}
