from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    # Entering the client shares one event loop across HTTP calls and websockets, as uvicorn does.
    # Without it each websocket gets its own loop and cross-socket broadcasts can hang.
    with TestClient(app) as c:
        yield c


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"ok": True}


def test_boards_seeded(client: TestClient) -> None:
    boards = client.get("/patients/p1/boards").json()
    assert any(b["id"] == "needs" for b in boards)


def test_signal_gesture_reaches_patient(client: TestClient) -> None:
    with client.websocket_connect("/ws/patient/p1") as patient:
        patient.receive_json()  # initial reliability snapshot
        with client.websocket_connect("/ws/signal?patient_id=p1") as sig:
            sig.send_json({"type": "gesture", "source": "eog_h", "gesture": "look_right", "confidence": 0.9, "ts": 1})
            msg = patient.receive_json()
    assert msg["type"] == "command" and msg["command"] == "RIGHT"


def test_mode_change_serializes_from(client: TestClient) -> None:
    with client.websocket_connect("/ws/patient/p1") as patient:
        patient.receive_json()
        patient.send_json({"type": "set_mode", "mode": "scan"})
        msg = patient.receive_json()
        patient.send_json({"type": "set_mode", "mode": "split"})
        patient.receive_json()
    assert msg == {"type": "mode_change", "from": "split", "to": "scan", "reason": "manual toggle"}


def test_jaw_hold_alerts_caregiver(client: TestClient) -> None:
    with client.websocket_connect("/ws/caregiver/p1") as caregiver:
        with client.websocket_connect("/ws/signal?patient_id=p1") as sig:
            sig.send_json({"type": "gesture", "source": "jaw", "gesture": "jaw_hold", "confidence": 0.9, "ts": 5})
            msg = caregiver.receive_json()
    assert msg["type"] == "alert" and msg["message"] == "HELP"


def test_login_checks_hashed_password(client: TestClient) -> None:
    assert client.post("/auth/login", json={"email": "caregiver@example.com", "password": "test-password"}).status_code == 200
    assert client.post("/auth/login", json={"email": "caregiver@example.com", "password": "wrong"}).status_code == 401


def test_pair_with_seeded_code(client: TestClient) -> None:
    r = client.post("/pair", json={"code": "123456"}).json()
    assert r["patient_id"] == "p1" and r["token"]
    assert client.post("/pair", json={"code": "000000"}).status_code == 404


def test_board_edit_persists_and_pushes_to_patient(client: TestClient) -> None:
    boards = client.get("/patients/p1/boards").json()
    edited = boards + [{"id": "test", "title": "Test", "items": ["Hello"]}]
    with client.websocket_connect("/ws/patient/p1") as patient:
        patient.receive_json()
        client.put("/patients/p1/boards", json=edited)
        pushed = patient.receive_json()
    assert pushed["type"] == "boards_updated" and pushed["boards"][-1]["id"] == "test"
    assert client.get("/patients/p1/boards").json() == edited
    client.put("/patients/p1/boards", json=boards)


def test_spoken_and_alert_saved_to_history(client: TestClient) -> None:
    with client.websocket_connect("/ws/patient/p1") as patient:
        patient.receive_json()
        patient.send_json({"type": "spoken", "text": "I need water", "ts": 100})
        patient.send_json({"type": "alert", "message": "HELP", "ts": 200})
        patient.send_json({"type": "set_mode", "mode": "scan"})  # round-trip to ensure both were handled
        patient.receive_json()
        patient.send_json({"type": "set_mode", "mode": "split"})
        patient.receive_json()
    history = client.get("/patients/p1/messages").json()
    assert {"spoken", "alert"} <= {m["type"] for m in history}
    assert any(m.get("text") == "I need water" for m in history)


def test_degrade_eye_expands_to_both_eye_signals(client: TestClient) -> None:
    with client.websocket_connect("/ws/signal?patient_id=p1") as sig:
        r = client.post("/demo/degrade", json={"signal": "eye", "factor": 0.3}).json()
        got = [sig.receive_json()["signal"], sig.receive_json()["signal"]]
    assert r["signals"] == ["eog_h", "blink"] and got == ["eog_h", "blink"]
