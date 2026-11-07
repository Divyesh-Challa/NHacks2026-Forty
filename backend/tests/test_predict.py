"""Prediction: uses the model when available, falls back on every failure, never auto-speaks."""

import asyncio
from types import SimpleNamespace

import anthropic
import httpx2 as httpx
import pytest

from app import db, predict
from app.models import PredictRequest

REQ = PredictRequest(patient_id="p1", recent_messages=["I need water"], time_of_day="08:00", present=["nurse"])


@pytest.fixture(autouse=True)
def _db() -> None:
    db.init_db()


class FakeMessages:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result, self.error, self.calls = result, error, []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


def fake_client(monkeypatch, **kw) -> FakeMessages:
    messages = FakeMessages(**kw)
    monkeypatch.setattr(predict, "_get_client", lambda: SimpleNamespace(messages=messages))
    return messages


def response(text: str, stop_reason: str = "end_turn"):
    return SimpleNamespace(
        stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)], _request_id="req_test"
    )


def run(req: PredictRequest = REQ) -> list[str]:
    return asyncio.run(predict.predict(req))


def test_no_api_key_returns_board_fallback(monkeypatch) -> None:
    monkeypatch.setattr(predict, "_get_client", lambda: None)
    assert run() == predict.fallback("p1")
    assert len(run()) == 5


def test_model_phrases_are_cleaned_and_capped(monkeypatch) -> None:
    text = '{"phrases": ["Good morning", "good morning", " Can I have breakfast? ", "", "Thank you", "Open the blinds", "I slept well", "Extra"]}'
    fake_client(monkeypatch, result=response(text))
    assert run() == ["Good morning", "Can I have breakfast?", "Thank you", "Open the blinds", "I slept well"]


def test_request_sends_only_recent_messages_and_json_schema(monkeypatch) -> None:
    messages = fake_client(monkeypatch, result=response('{"phrases": ["A", "B", "C"]}'))
    run(PredictRequest(patient_id="p1", recent_messages=[f"m{i}" for i in range(20)]))
    sent = messages.calls[0]
    prompt = sent["messages"][0]["content"]
    assert "m19" in prompt and "m14" not in prompt  # last 5 only
    assert sent["output_config"]["format"]["type"] == "json_schema"


def test_too_few_phrases_topped_up_from_fallback(monkeypatch) -> None:
    fake_client(monkeypatch, result=response('{"phrases": ["Hello"]}'))
    out = run()
    assert out[0] == "Hello" and len(out) == 3


@pytest.mark.parametrize(
    "error",
    [
        anthropic.APITimeoutError(request=httpx.Request("POST", "https://api.anthropic.com")),
        anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com")),
    ],
)
def test_network_failures_fall_back(monkeypatch, error) -> None:
    fake_client(monkeypatch, error=error)
    assert run() == predict.fallback("p1")


def test_refusal_and_bad_json_fall_back(monkeypatch) -> None:
    fake_client(monkeypatch, result=response("", stop_reason="refusal"))
    assert run() == predict.fallback("p1")
    fake_client(monkeypatch, result=response("not json"))
    assert run() == predict.fallback("p1")
