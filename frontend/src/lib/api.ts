// REST helpers + backend URLs. Override with VITE_API_URL for phone testing on the LAN.
import type { Board } from './types'

export const API_URL: string = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
export const WS_URL = API_URL.replace(/^http/, 'ws')

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) throw new Error(`${res.status} ${path}`)
  return res.json() as Promise<T>
}

export const getBoards = (patientId: string) => json<Board[]>(`/patients/${patientId}/boards`)
export const getConfig = () => json<{ ui: { scan_interval_ms: number } }>('/config')
export const login = (email: string, password: string) =>
  json<{ token: string }>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
export const pair = (code: string) =>
  json<{ patient_id: string; token: string }>('/pair', { method: 'POST', body: JSON.stringify({ code }) })
export const predict = (patient_id: string, recent_messages: string[]) =>
  json<{ phrases: string[] }>('/predict', {
    method: 'POST',
    body: JSON.stringify({ patient_id, recent_messages, time_of_day: new Date().toTimeString().slice(0, 5) }),
  })
