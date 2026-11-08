"""Context-aware phrase prediction.

Suggestions only. Nothing here is ever spoken; the patient must SELECT a phrase first.
Calls the Anthropic API with a hard PREDICT["timeout_s"] timeout and no retries; on any failure
(no key, timeout, network, refusal, bad JSON) returns a fallback list from the patient's boards.
"""

import json
import logging

import anthropic

from .config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, PREDICT
from .db import get_boards
from .models import PredictRequest

log = logging.getLogger("relay.predict")

MIN_PHRASES, MAX_PHRASES = 3, 5
MAX_PHRASE_CHARS = 60

SYSTEM = """You suggest phrases for a person with ALS who communicates through an AAC board by \
selecting items with eye movement or blinking. Each selection is slow and tiring, so a good \
suggestion saves them real effort.

Suggest 3 to 5 short phrases they are likely to want to say next, written in the first person \
as they would say them aloud (for example "I need water" or "Can you turn on the light?"). \
Keep each phrase under 8 words. Use the recent messages, the time of day, and who is present \
to make the suggestions specific; vary them rather than rephrasing one idea. Prefer everyday \
needs, comfort, and social phrases. Never suggest anything medical-sounding as a statement of \
fact about their condition."""

SCHEMA = {
    "type": "object",
    "properties": {"phrases": {"type": "array", "items": {"type": "string"}}},
    "required": ["phrases"],
    "additionalProperties": False,
}

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic | None:
    global _client
    if not ANTHROPIC_API_KEY:
        return None
    if _client is None:
        _client = anthropic.AsyncAnthropic(
            api_key=ANTHROPIC_API_KEY, timeout=PREDICT["timeout_s"], max_retries=0
        )
    return _client


def fallback(patient_id: str) -> list[str]:
    boards = get_boards(patient_id)
    items = [i for b in boards for i in b["items"]]
    return items[:MAX_PHRASES]


def _user_prompt(req: PredictRequest) -> str:
    recent = req.recent_messages[-PREDICT["max_recent_messages"] :]
    lines = [
        f"Time of day: {req.time_of_day or 'unknown'}",
        f"Present: {', '.join(req.present) if req.present else 'unknown'}",
        "Recent messages (oldest first):",
        *([f"- {m}" for m in recent] or ["- (none yet)"]),
    ]
    return "\n".join(lines)


def _clean(phrases: list[str]) -> list[str]:
    out: list[str] = []
    for p in phrases:
        p = p.strip().strip('"')
        if p and len(p) <= MAX_PHRASE_CHARS and p.lower() not in {o.lower() for o in out}:
            out.append(p)
    return out[:MAX_PHRASES]


async def predict(req: PredictRequest) -> list[str]:
    client = _get_client()
    if client is None:
        return fallback(req.patient_id)
    try:
        response = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1024,
            system=SYSTEM,
            messages=[{"role": "user", "content": _user_prompt(req)}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        )
        if response.stop_reason == "refusal":
            log.warning("prediction refused (%s)", response._request_id)
            return fallback(req.patient_id)
        text = next(b.text for b in response.content if b.type == "text")
        phrases = _clean(json.loads(text)["phrases"])
    except anthropic.APITimeoutError:
        log.warning("prediction timed out after %ss; using fallback", PREDICT["timeout_s"])
        return fallback(req.patient_id)
    except anthropic.APIConnectionError:
        log.warning("prediction network error; using fallback")
        return fallback(req.patient_id)
    except anthropic.APIStatusError as e:
        log.warning("prediction API error %s: %s", e.status_code, e.message)
        return fallback(req.patient_id)
    except (StopIteration, KeyError, TypeError, json.JSONDecodeError) as e:
        log.warning("prediction returned unusable output (%r); using fallback", e)
        return fallback(req.patient_id)

    if len(phrases) < MIN_PHRASES:
        phrases += [p for p in fallback(req.patient_id) if p not in phrases][: MIN_PHRASES - len(phrases)]
    return phrases
