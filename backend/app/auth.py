"""Caregiver JWT auth + patient pairing.

Caregivers (bcrypt-hashed) and patient pair codes live in the DB (db.py).
Caregiver tokens carry the patient they look after; `require_caregiver` checks it on
caregiver-only routes, and `caregiver_for_ws` does the same for the caregiver WebSocket (?token=).
The patient screen has no login (it pairs once with a code), so patient routes stay open.
"""

import time

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import db
from .config import JWT_SECRET

_bearer = HTTPBearer(auto_error=False)


def issue_token(sub: str, role: str, patient_id: str, ttl_s: int = 7 * 24 * 3600) -> str:
    claims = {"sub": sub, "role": role, "patient_id": patient_id, "exp": int(time.time()) + ttl_s}
    return jwt.encode(claims, JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def login(email: str, password: str) -> tuple[str, str] | None:
    """Returns (patient_id, token) for valid caregiver credentials."""
    caregiver = db.get_caregiver(email)
    if caregiver and db.check_password(password, caregiver.password_hash):
        return caregiver.patient_id, issue_token(email, "caregiver", caregiver.patient_id)
    return None


def pair(code: str) -> tuple[str, str] | None:
    """Returns (patient_id, token) for a valid code."""
    patient = db.get_patient_by_code(code)
    if patient:
        return patient.id, issue_token(patient.id, "patient", patient.id, ttl_s=365 * 24 * 3600)
    return None


def caregiver_for_ws(token: str | None, patient_id: str) -> bool:
    claims = decode_token(token) if token else None
    return bool(claims and claims.get("role") == "caregiver" and claims.get("patient_id") == patient_id)


def require_caregiver(
    patient_id: str, creds: HTTPAuthorizationCredentials | None = Depends(_bearer)
) -> dict:
    """FastAPI dependency for routes with a {patient_id} path param."""
    claims = decode_token(creds.credentials) if creds else None
    if not claims or claims.get("role") != "caregiver":
        raise HTTPException(401, "caregiver login required")
    if claims.get("patient_id") != patient_id:
        raise HTTPException(403, "not this patient's caregiver")
    return claims
