"""Caregiver JWT auth + patient pairing. Owner: Role D. Time-box ~2 h.

SCAFFOLD STATUS: accepts the demo caregiver / demo pair code, issues real JWTs.
TODO: bcrypt-hashed caregivers in DB, generated 6-digit codes, `require_caregiver` dependency on routes.
"""

import time

import jwt

from .config import DEMO_CAREGIVER_PASSWORD, JWT_SECRET
from .seed import DEMO_CAREGIVER_EMAIL, DEMO_PAIR_CODE, DEMO_PATIENT_ID


def issue_token(sub: str, role: str, ttl_s: int = 7 * 24 * 3600) -> str:
    return jwt.encode({"sub": sub, "role": role, "exp": int(time.time()) + ttl_s}, JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])


def login(email: str, password: str) -> str | None:
    if email == DEMO_CAREGIVER_EMAIL and password == DEMO_CAREGIVER_PASSWORD:
        return issue_token(email, "caregiver")
    return None


def pair(code: str) -> tuple[str, str] | None:
    """Returns (patient_id, token) for a valid code."""
    if code == DEMO_PAIR_CODE:
        return DEMO_PATIENT_ID, issue_token(DEMO_PATIENT_ID, "patient", ttl_s=365 * 24 * 3600)
    return None
