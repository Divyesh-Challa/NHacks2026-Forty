"""SQLite persistence via SQLModel. Tables are created and seeded on first start.

The functions below are the only DB API the rest of the app uses.
"""

import json

import bcrypt
from sqlmodel import Field, Session, SQLModel, create_engine, select

from .config import DATABASE_URL, DEMO_CAREGIVER_PASSWORD
from .seed import DEFAULT_BOARDS, DEMO_CAREGIVER_EMAIL, DEMO_PAIR_CODE, DEMO_PATIENT_ID, DEMO_PATIENT_NAME


class Patient(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    pair_code: str = Field(index=True)


class Caregiver(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    password_hash: str
    patient_id: str = Field(foreign_key="patient.id")


class BoardRow(SQLModel, table=True):
    __tablename__ = "board"
    pk: int | None = Field(default=None, primary_key=True)
    patient_id: str = Field(foreign_key="patient.id", index=True)
    position: int
    board_id: str
    title: str
    items_json: str  # JSON list of phrases


class Message(SQLModel, table=True):
    """Every spoken phrase and alert, stored as its wire-format payload."""

    id: int | None = Field(default=None, primary_key=True)
    patient_id: str = Field(index=True)
    type: str
    ts: int = Field(index=True)
    payload_json: str


class Calibration(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    patient_id: str = Field(index=True)
    signal: str
    accuracy: float
    false_trigger_rate: float


engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def init_db() -> None:
    """Create tables and seed the fake demo patient/caregiver/boards if the DB is empty."""
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        if s.get(Patient, DEMO_PATIENT_ID):
            return
        s.add(Patient(id=DEMO_PATIENT_ID, name=DEMO_PATIENT_NAME, pair_code=DEMO_PAIR_CODE))
        s.add(
            Caregiver(
                email=DEMO_CAREGIVER_EMAIL,
                password_hash=hash_password(DEMO_CAREGIVER_PASSWORD),
                patient_id=DEMO_PATIENT_ID,
            )
        )
        s.commit()
    set_boards(DEMO_PATIENT_ID, DEFAULT_BOARDS)


def get_boards(patient_id: str) -> list[dict]:
    with Session(engine) as s:
        rows = s.exec(select(BoardRow).where(BoardRow.patient_id == patient_id).order_by(BoardRow.position)).all()
        return [{"id": r.board_id, "title": r.title, "items": json.loads(r.items_json)} for r in rows]


def set_boards(patient_id: str, boards: list[dict]) -> None:
    with Session(engine) as s:
        for r in s.exec(select(BoardRow).where(BoardRow.patient_id == patient_id)).all():
            s.delete(r)
        for i, b in enumerate(boards):
            s.add(
                BoardRow(
                    patient_id=patient_id,
                    position=i,
                    board_id=b["id"],
                    title=b["title"],
                    items_json=json.dumps(b["items"]),
                )
            )
        s.commit()


def add_message(patient_id: str, msg: dict) -> None:
    with Session(engine) as s:
        s.add(Message(patient_id=patient_id, type=msg["type"], ts=msg["ts"], payload_json=json.dumps(msg)))
        s.commit()


def get_messages(patient_id: str, limit: int = 200) -> list[dict]:
    """Most recent first."""
    with Session(engine) as s:
        rows = s.exec(
            select(Message).where(Message.patient_id == patient_id).order_by(Message.ts.desc()).limit(limit)
        ).all()
        return [json.loads(r.payload_json) for r in rows]


def add_calibration(row: dict) -> None:
    with Session(engine) as s:
        s.add(Calibration(**row))
        s.commit()


def get_caregiver(email: str) -> Caregiver | None:
    with Session(engine) as s:
        return s.exec(select(Caregiver).where(Caregiver.email == email)).first()


def get_patient_by_code(code: str) -> Patient | None:
    with Session(engine) as s:
        return s.exec(select(Patient).where(Patient.pair_code == code)).first()
