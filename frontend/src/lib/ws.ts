// Reconnecting WebSocket client with typed messages.
import { WS_URL } from './api'
import { normalizeEvent } from './normalize'
import type { PatientEvent, ServerEvent } from './types'

export interface RelaySocket {
  send: (ev: PatientEvent) => void
  close: () => void
}

export function connect(
  path: string,
  onMessage: (ev: ServerEvent) => void,
  onStatus?: (connected: boolean) => void,
): RelaySocket {
  let ws: WebSocket | null = null
  let closed = false
  let retry: ReturnType<typeof setTimeout> | undefined

  const open = () => {
    ws = new WebSocket(`${WS_URL}${path}`)
    ws.onopen = () => onStatus?.(true)
    ws.onmessage = (e) => onMessage(normalizeEvent(JSON.parse(e.data)))
    ws.onclose = () => {
      onStatus?.(false)
      if (!closed) retry = setTimeout(open, 1500)
    }
  }
  open()

  return {
    send: (ev) => {
      if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(ev))
    },
    close: () => {
      closed = true
      clearTimeout(retry)
      ws?.close()
    },
  }
}
