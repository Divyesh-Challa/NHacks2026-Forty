"""Relay backend. Run: uvicorn app.main:app --reload --port 8000 (from backend/)."""

import logging

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import auth, db, predict
from .config import INPUT, UI
from .models import Board, CalibrationRequest, DegradeRequest, LoginRequest, PairRequest, PredictRequest, PredictResponse
from .ws import hub, router as ws_router

logging.basicConfig(level=logging.INFO)

DEMO_SIGNAL_GROUPS = {"eye": ["eog_h", "blink"]}

db.init_db()

app = FastAPI(title="Relay")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(ws_router)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/config")
def config() -> dict:
    return {"ui": UI, "input": INPUT}


@app.post("/auth/login")
def login(body: LoginRequest) -> dict:
    result = auth.login(body.email, body.password)
    if not result:
        raise HTTPException(401, "invalid credentials")
    patient_id, token = result
    return {"patient_id": patient_id, "token": token}


@app.post("/pair")
def pair(body: PairRequest) -> dict:
    result = auth.pair(body.code)
    if not result:
        raise HTTPException(404, "unknown code")
    patient_id, token = result
    return {"patient_id": patient_id, "token": token}


@app.get("/patients/{patient_id}/boards")
def get_boards(patient_id: str) -> list[Board]:
    return [Board(**b) for b in db.get_boards(patient_id)]


@app.put("/patients/{patient_id}/boards", dependencies=[Depends(auth.require_caregiver)])
async def put_boards(patient_id: str, boards: list[Board]) -> list[Board]:
    db.set_boards(patient_id, [b.model_dump() for b in boards])
    await hub.to_patient(patient_id, {"type": "boards_updated", "boards": [b.model_dump() for b in boards]})
    return boards


@app.post("/predict")
async def post_predict(body: PredictRequest) -> PredictResponse:
    return PredictResponse(phrases=await predict.predict(body))


@app.post("/calibration")
def post_calibration(body: CalibrationRequest) -> dict:
    db.add_calibration(body.model_dump(mode="json"))
    return {"ok": True}


@app.get("/patients/{patient_id}/messages", dependencies=[Depends(auth.require_caregiver)])
def get_messages(patient_id: str) -> list[dict]:
    return db.get_messages(patient_id)


@app.post("/demo/degrade")
async def demo_degrade(body: DegradeRequest, patient_id: str = "p1") -> dict:
    """Demo only: tell the signal service to scale a signal's gain down.

    "eye" degrades both eye-electrode signals (eog_h + blink) in one call — the stage demo uses it
    to go straight from eye-movement wheel mode to jaw-clench scan mode.
    """
    signals = DEMO_SIGNAL_GROUPS.get(body.signal, [body.signal])
    for signal in signals:
        await hub.to_signal(patient_id, {"type": "degrade", "signal": signal, "factor": body.factor})
    return {"ok": True, "signals": signals}
