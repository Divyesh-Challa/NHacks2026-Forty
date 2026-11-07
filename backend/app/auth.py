"""Caregiver JWT auth + patient pairing. Owner: Role D. Time-box ~2 h.

Caregivers (bcrypt-hashed) and patient pair codes live in the DB (db.py); JWTs are real.
TODO (Role D): generated 6-digit codes, `require_caregiver` dependency on caregiver routes + WS.
"""

import time

import jwt

from . import db
from .config import JWT_SECRET


def issue_token(sub: str, role: str, ttl_s: int = 7 * 24 * 3600) -> str:
    return jwt.encode({"sub": sub, "role": role, "exp": int(time.time()) + ttl_s}, JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])


def login(email: str, password: str) -> str | None:
    caregiver = db.get_caregiver(email)
    if caregiver and db.check_password(password, caregiver.password_hash):
        return issue_token(email, "caregiver")
    return None


def pair(code: str) -> tuple[str, str] | None:
    """Returns (patient_id, token) for a valid code."""
    patient = db.get_patient_by_code(code)
    if patient:
        return patient.id, issue_token(patient.id, "patient", ttl_s=365 * 24 * 3600)
    return None
