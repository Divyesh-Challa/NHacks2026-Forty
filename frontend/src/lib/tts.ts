// Text-to-speech via the browser Web Speech API.
// speak(): the real voice. Only call this after an explicit SELECT — never speak unconfirmed text.
// aid(): the audio aid (option read-outs, read-back). Quieter, faster and preceded by a tone so it
// never sounds like a message, and it never interrupts the real voice.
let realSpeaking = false

export function speak(text: string): void {
  if (!('speechSynthesis' in window)) return
  window.speechSynthesis.cancel()
  const u = new SpeechSynthesisUtterance(text)
  u.rate = 0.95
  u.onend = u.onerror = () => {
    realSpeaking = false
  }
  realSpeaking = true
  window.speechSynthesis.speak(u)
}

let audio: AudioContext | undefined

function tone(): void {
  try {
    audio ??= new AudioContext()
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

export function aid(text: string): void {
  if (!('speechSynthesis' in window) || realSpeaking) return
  tone()
  window.speechSynthesis.cancel() // only an earlier aid utterance can be playing here
  const u = new SpeechSynthesisUtterance(text)
  u.volume = 0.5
  u.rate = 1.3
  window.speechSynthesis.speak(u)
}
