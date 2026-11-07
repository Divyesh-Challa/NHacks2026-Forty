from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    assert client.get("/health").json() == {"ok": True}


def test_boards_seeded() -> None:
    boards = client.get("/patients/p1/boards").json()
    assert any(b["id"] == "needs" for b in boards)


def test_signal_gesture_reaches_patient() -> None:
    with client.websocket_connect("/ws/patient/p1") as patient:
        patient.receive_json()  # initial reliability snapshot
        with client.websocket_connect("/ws/signal?patient_id=p1") as sig:
            sig.send_json({"type": "gesture", "source": "eog_h", "gesture": "look_right", "confidence": 0.9, "ts": 1})
            msg = patient.receive_json()
    assert msg["type"] == "command" and msg["command"] == "RIGHT"


def test_mode_change_serializes_from() -> None:
    with client.websocket_connect("/ws/patient/p1") as patient:
        patient.receive_json()
        patient.send_json({"type": "set_mode", "mode": "scan"})
        msg = patient.receive_json()
        patient.send_json({"type": "set_mode", "mode": "split"})
        patient.receive_json()
    assert msg == {"type": "mode_change", "from": "split", "to": "scan", "reason": "manual toggle"}


def test_jaw_hold_alerts_caregiver() -> None:
    with client.websocket_connect("/ws/caregiver/p1") as caregiver:
        with client.websocket_connect("/ws/signal?patient_id=p1") as sig:
            sig.send_json({"type": "gesture", "source": "jaw", "gesture": "jaw_hold", "confidence": 0.9, "ts": 5})
            msg = caregiver.receive_json()
    assert msg["type"] == "alert" and msg["message"] == "HELP"
