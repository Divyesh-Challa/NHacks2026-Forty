"""Context-aware phrase prediction. Owner: Role D.

Never auto-speaks: these are suggestions only.
SCAFFOLD STATUS: returns the fallback list.
TODO: call Anthropic (ANTHROPIC_MODEL) with a PREDICT["timeout_s"] timeout, ask for 3-5 short
first-person phrases as JSON from the last PREDICT["max_recent_messages"] messages, time of day,
and who is present; fall back on any error or missing key.
"""

from .config import PREDICT  # noqa: F401  (used once implemented)
from .db import get_boards
from .models import PredictRequest


def fallback(patient_id: str) -> list[str]:
    boards = get_boards(patient_id)
    items = [i for b in boards for i in b["items"]]
    return items[:5]


async def predict(req: PredictRequest) -> list[str]:
    return fallback(req.patient_id)
