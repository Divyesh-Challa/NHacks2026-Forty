// Text-to-speech via the browser Web Speech API.
// Only call this after an explicit SELECT — never speak unconfirmed text.
export function speak(text: string): void {
  if (!('speechSynthesis' in window)) return
  window.speechSynthesis.cancel()
  const u = new SpeechSynthesisUtterance(text)
  u.rate = 0.95
  window.speechSynthesis.speak(u)
}
