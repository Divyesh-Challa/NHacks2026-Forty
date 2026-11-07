// Wire-format types — the interface contract from CLAUDE.md.
// Mirrors backend/app/models.py by hand. Change both (and CLAUDE.md) together and tell the team.

export type Command = 'LEFT' | 'RIGHT' | 'SELECT' | 'BACK' | 'HELP'
export type Mode = 'split' | 'scan'

export interface CommandEvent {
  type: 'command'
  command: Command
  via: string
  confidence: number
  ts: number
}

export interface ReliabilityEvent {
  type: 'reliability'
  signals: Record<string, number>
  mode: Mode
  mapping: Partial<Record<Command, string>>
}

export interface ModeChangeEvent {
  type: 'mode_change'
  from: Mode
  to: Mode
  reason: string
}

export interface AlertEvent {
  type: 'alert'
  level: 'urgent' | 'info'
  patient_id: string
  message: string
  ts: number
}

export interface SpokenEvent {
  type: 'spoken'
  patient_id: string
  text: string
  ts: number
}

export interface BoardsUpdatedEvent {
  type: 'boards_updated'
  boards: Board[]
}

export type ServerEvent =
  | CommandEvent
  | ReliabilityEvent
  | ModeChangeEvent
  | AlertEvent
  | SpokenEvent
  | BoardsUpdatedEvent

// Patient screen -> backend
export type PatientEvent =
  | { type: 'spoken'; text: string; ts: number }
  | { type: 'alert'; message: string; ts: number }
  | { type: 'set_mode'; mode: Mode }

export interface Board {
  id: string
  title: string
  items: string[]
}
