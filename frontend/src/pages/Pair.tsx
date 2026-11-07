// One-time patient device pairing via 6-digit code (entered by a caregiver). Owner: Role D.
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { pair } from '../lib/api'

export default function Pair() {
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const nav = useNavigate()
  return (
    <main className="caregiver">
      <h1>Pair this device</h1>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          pair(code)
            .then((r) => {
              localStorage.setItem('relay_patient_token', r.token)
              nav(`/patient/${r.patient_id}`)
            })
            .catch(() => setError('Unknown code'))
        }}
      >
        <input value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" maxLength={6} placeholder="6-digit code" />
        <button type="submit">Pair</button>
        {error && <p className="error">{error}</p>}
      </form>
    </main>
  )
}
