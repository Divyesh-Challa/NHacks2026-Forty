// REST helpers + backend URLs. Override with VITE_API_URL for phone testing on the LAN.
import type { AlertEvent, Board, SpokenEvent } from './types'

export type HistoryItem = AlertEvent | SpokenEvent

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
export const getConfig = () =>
  json<{ ui: { scan_interval_ms: number }; input: { reliability_cutoff: number } }>('/config')
export const login = (email: string, password: string) =>
  json<{ patient_id: string; token: string }>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
export const pair = (code: string) =>
  json<{ patient_id: string; token: string }>('/pair', { method: 'POST', body: JSON.stringify({ code }) })
export const predict = (patient_id: string, recent_messages: string[]) =>
  json<{ phrases: string[] }>('/predict', {
    method: 'POST',
    body: JSON.stringify({ patient_id, recent_messages, time_of_day: new Date().toTimeString().slice(0, 5) }),
  })
export const degrade = (signal: 'eye' | 'eog_h' | 'blink' | 'jaw', factor: number) =>
  json<{ ok: boolean; signals: string[] }>('/demo/degrade', { method: 'POST', body: JSON.stringify({ signal, factor }) })

// Caregiver-only routes (need the login token). A 401 means the token expired or is invalid.
export class Unauthorized extends Error {}

async function authed<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
  })
  if (res.status === 401) throw new Unauthorized()
  if (!res.ok) throw new Error(`${res.status} ${path}`)
  return res.json() as Promise<T>
}

export const getMessages = (patientId: string, token: string) =>
  authed<HistoryItem[]>(`/patients/${patientId}/messages`, token)
export const putBoards = (patientId: string, boards: Board[], token: string) =>
  authed<Board[]>(`/patients/${patientId}/boards`, token, { method: 'PUT', body: JSON.stringify(boards) })
