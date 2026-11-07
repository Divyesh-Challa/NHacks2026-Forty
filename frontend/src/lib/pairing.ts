// Patient device pairing: the token /pair stored, if it is for this patient. Display-only decode (no verification).
const TOKEN_KEY = 'relay_patient_token'

// Returns the stored token only when its patient_id claim matches `patientId` and it has not expired.
export function pairedToken(patientId: string): string | null {
  try {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) return null
    const payload = token.split('.')[1]
    if (!payload) return null
    const b64 = payload.replace(/-/g, '+').replace(/_/g, '/')
    const claims = JSON.parse(atob(b64.padEnd(Math.ceil(b64.length / 4) * 4, '='))) as { patient_id?: unknown; exp?: unknown }
    if (claims.patient_id !== patientId) return null
    if (typeof claims.exp === 'number' && claims.exp * 1000 < Date.now()) return null
    return token
  } catch {
    return null
  }
}
