"""Wire-format models. This is the interface contract from CLAUDE.md.

Mirrored by hand in frontend/src/lib/types.ts and signal/messages.py —
change all three together (and CLAUDE.md) and tell the team.
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Command(str, Enum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    SELECT = "SELECT"
    BACK = "BACK"
    HELP = "HELP"


class Source(str, Enum):
    eog_h = "eog_h"
    eog_v = "eog_v"
    blink = "blink"
    jaw = "jaw"
    brow = "brow"
    sim = "sim"


class Gesture(str, Enum):
    look_left = "look_left"
    look_right = "look_right"
    look_up = "look_up"
    look_down = "look_down"
    blink_double = "blink_double"
    jaw_clench = "jaw_clench"
    jaw_hold = "jaw_hold"
    brow_raise = "brow_raise"


Mode = Literal["split", "scan"]


# --- signal service -> backend (/ws/signal) ---

class GestureEvent(BaseModel):
    type: Literal["gesture"] = "gesture"
    source: Source
    gesture: Gesture
    confidence: float
    ts: int


class SignalReliabilityEvent(BaseModel):
    type: Literal["reliability"] = "reliability"
    signals: dict[str, float]
    ts: int


# --- backend -> frontend (/ws/patient/{id}, /ws/caregiver/{id}) ---

class CommandEvent(BaseModel):
    type: Literal["command"] = "command"
    command: Command
    via: str
    confidence: float
    ts: int


class ReliabilityEvent(BaseModel):
    type: Literal["reliability"] = "reliability"
    signals: dict[str, float]
    mode: Mode
    mapping: dict[str, str]


class ModeChangeEvent(BaseModel):
    """Serialize with model_dump(by_alias=True) so `from_` goes out as "from"."""

    model_config = ConfigDict(populate_by_name=True)

    type: Literal["mode_change"] = "mode_change"
    from_: Mode = Field(alias="from")
    to: Mode
    reason: str


class AlertEvent(BaseModel):
    type: Literal["alert"] = "alert"
    level: Literal["urgent", "info"] = "urgent"
    patient_id: str
    message: str
    ts: int


class SpokenEvent(BaseModel):
    type: Literal["spoken"] = "spoken"
    patient_id: str
    text: str
    ts: int


# --- REST bodies ---

class LoginRequest(BaseModel):
    email: str
    password: str


class PairRequest(BaseModel):
    code: str


class PredictRequest(BaseModel):
    patient_id: str
    recent_messages: list[str] = []
    time_of_day: str | None = None
    present: list[str] = []


class PredictResponse(BaseModel):
    phrases: list[str]


class CalibrationRequest(BaseModel):
    patient_id: str
    signal: Source
    accuracy: float
    false_trigger_rate: float


class DegradeRequest(BaseModel):
    signal: Source
    factor: float


class Board(BaseModel):
    id: str
    title: str
    items: list[str]
