"""SQLite persistence. Owner: Role A.

SCAFFOLD STATUS: in-memory store so REST routes return data today.
TODO: SQLModel tables (Patient, Caregiver, Board, Message, Calibration), init_db(), seed on startup.
"""

import copy

from .seed import DEFAULT_BOARDS, DEMO_PATIENT_ID

_boards: dict[str, list[dict]] = {DEMO_PATIENT_ID: copy.deepcopy(DEFAULT_BOARDS)}
_messages: dict[str, list[dict]] = {DEMO_PATIENT_ID: []}
_calibration: list[dict] = []


def get_boards(patient_id: str) -> list[dict]:
    return _boards.get(patient_id, copy.deepcopy(DEFAULT_BOARDS))


def set_boards(patient_id: str, boards: list[dict]) -> None:
    _boards[patient_id] = boards


def add_message(patient_id: str, msg: dict) -> None:
    _messages.setdefault(patient_id, []).append(msg)


def get_messages(patient_id: str) -> list[dict]:
    return _messages.get(patient_id, [])


def add_calibration(row: dict) -> None:
    _calibration.append(row)
