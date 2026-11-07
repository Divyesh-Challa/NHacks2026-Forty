"""WebSocket hub: signal service -> input manager -> patient + caregiver screens.

Endpoints:
  /ws/signal?patient_id=p1     signal service sends gesture/reliability; receives `degrade` controls
  /ws/patient/{patient_id}     patient screen receives commands etc.; sends `spoken` / `alert`
  /ws/caregiver/{patient_id}   caregiver screen receives alerts, spoken, reliability, mode_change
"""

import logging
import time
from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from . import db
from .input_manager import InputManager
from .models import AlertEvent, GestureEvent, SignalReliabilityEvent, SpokenEvent

log = logging.getLogger("relay.ws")
router = APIRouter()


def now_ms() -> int:
    return int(time.time() * 1000)


class Hub:
    def __init__(self) -> None:
        self.patients: dict[str, set[WebSocket]] = defaultdict(set)
        self.caregivers: dict[str, set[WebSocket]] = defaultdict(set)
        self.signals: dict[str, set[WebSocket]] = defaultdict(set)
        self.managers: dict[str, InputManager] = {}

    def manager(self, patient_id: str) -> InputManager:
        return self.managers.setdefault(patient_id, InputManager())

    async def _send(self, sockets: set[WebSocket], payload: dict) -> None:
        for ws in list(sockets):
            try:
                await ws.send_json(payload)
            except Exception:
                sockets.discard(ws)

    async def to_patient(self, patient_id: str, ev: BaseModel | dict) -> None:
        await self._send(self.patients[patient_id], _dump(ev))

    async def to_caregiver(self, patient_id: str, ev: BaseModel | dict) -> None:
        await self._send(self.caregivers[patient_id], _dump(ev))

    async def to_both(self, patient_id: str, ev: BaseModel | dict) -> None:
        await self.to_patient(patient_id, ev)
        await self.to_caregiver(patient_id, ev)

    async def to_signal(self, patient_id: str, payload: dict) -> None:
        await self._send(self.signals[patient_id], payload)


def _dump(ev: BaseModel | dict) -> dict:
    return ev.model_dump(mode="json", by_alias=True) if isinstance(ev, BaseModel) else ev


hub = Hub()


@router.websocket("/ws/signal")
async def ws_signal(ws: WebSocket, patient_id: str = "p1") -> None:
    await ws.accept()
    hub.signals[patient_id].add(ws)
    im = hub.manager(patient_id)
    try:
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "gesture":
                ev = GestureEvent.model_validate(msg)
                log.info("gesture %s/%s %.2f", ev.source.value, ev.gesture.value, ev.confidence)
                for cmd in im.on_gesture(ev):
                    await hub.to_patient(patient_id, cmd)
            elif msg.get("type") == "reliability":
                for out in im.on_reliability(SignalReliabilityEvent.model_validate(msg)):
                    await hub.to_both(patient_id, out)
    except WebSocketDisconnect:
        hub.signals[patient_id].discard(ws)


@router.websocket("/ws/patient/{patient_id}")
async def ws_patient(ws: WebSocket, patient_id: str) -> None:
    await ws.accept()
    hub.patients[patient_id].add(ws)
    await ws.send_json(_dump(hub.manager(patient_id).snapshot()))
    try:
        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")
            if kind == "spoken":
                ev = SpokenEvent(patient_id=patient_id, text=msg["text"], ts=msg.get("ts", now_ms()))
                db.add_message(patient_id, _dump(ev))
                await hub.to_caregiver(patient_id, ev)
            elif kind == "alert":
                ev = AlertEvent(patient_id=patient_id, message=msg.get("message", "HELP"), ts=msg.get("ts", now_ms()))
                db.add_message(patient_id, _dump(ev))
                await hub.to_caregiver(patient_id, ev)
            elif kind == "set_mode":  # keyboard-sim mode toggle
                change = hub.manager(patient_id).force_mode(msg["mode"])
                if change:
                    await hub.to_both(patient_id, change)
    except WebSocketDisconnect:
        hub.patients[patient_id].discard(ws)


@router.websocket("/ws/caregiver/{patient_id}")
async def ws_caregiver(ws: WebSocket, patient_id: str) -> None:
    # TODO (Role D): require a caregiver JWT via ?token=
    await ws.accept()
    hub.caregivers[patient_id].add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.caregivers[patient_id].discard(ws)
