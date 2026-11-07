// Text-to-speech via the browser Web Speech API.
// speak(): the real voice. Only call this after an explicit SELECT — never speak unconfirmed text.
// aid(): the audio aid (option read-outs, read-back). Quieter, faster and preceded by a tone so it
// never sounds like a message, and it never interrupts the real voice.
let realSpeaking = false
let keepPlaying = false // a read-back is playing; later aids queue behind it instead of cutting it off
// Held at module level: Chrome can garbage-collect an unreferenced utterance and never fire onend.
let current: SpeechSynthesisUtterance | undefined

export function speak(text: string): void {
  if (!('speechSynthesis' in window)) return
  window.speechSynthesis.cancel()
  const u = new SpeechSynthesisUtterance(text)
  u.rate = 0.95
  u.onend = u.onerror = () => {
    realSpeaking = false
  }
  realSpeaking = true
  current = u
  window.speechSynthesis.speak(u)
}

let audio: AudioContext | undefined

function tone(): void {
  try {
    audio ??= new AudioContext()
    // Created before any user gesture, the context starts suspended and stays silent until resumed.
    if (audio.state === 'suspended') void audio.resume()
    const osc = audio.createOscillator()
    const gain = audio.createGain()
    osc.frequency.value = 880
    gain.gain.value = 0.05
    osc.connect(gain).connect(audio.destination)
    osc.start()
    osc.stop(audio.currentTime + 0.08)
  } catch {
    // No Web Audio: the aid still speaks.
  }
}

// keep: a read-back the person must hear in full before confirming.
export function aid(text: string, keep = false): void {
  if (!('speechSynthesis' in window)) return
  const synth = window.speechSynthesis
  // `speaking` covers a real utterance whose onend never fired.
  if (realSpeaking && synth.speaking) return
  realSpeaking = false
  tone()
  if (!(keepPlaying && synth.speaking)) synth.cancel() // only an earlier aid utterance can be playing here
  const u = new SpeechSynthesisUtterance(text)
  u.volume = 0.5
  u.rate = 1.3
  if (keep) {
    keepPlaying = true
    u.onend = u.onerror = () => {
      keepPlaying = false
    }
  }
  current = u
  synth.speak(u)
}

// Read by nothing; exists so the latest utterance stays referenced.
export const lastUtterance = () => current
