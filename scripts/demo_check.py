"""End-to-end check of the 3-step stage demo, with no hardware and no browser.

Starts the backend on a spare port with a throwaway database, then plays the signal service
(gestures + reliability, honouring `degrade` controls) and listens as the patient screen and the
caregiver phone. Exits non-zero if any step fails.

    make demo-check          # or: backend/.venv/bin/python scripts/demo_check.py
"""

import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
PATIENT = "p1"
PASSWORD = "demo-check-password"
RELIABILITY_HZ = 20  # faster than the real ~1 Hz so the 10-reading remap takes ~0.5 s
# Readings by which a degrade reaches each signal. The real detectors never lose eog_h and blink on
# the same reading, so blink trails: the stage banner must still be one split -> scan change.
LAG = {"blink": 3}
EYE_TO_JAW = "Eye movement and blinking reliability fell below 60%. Switching to scan mode with jaw clench to select."
EYE_BACK = "Eye movement and blinking are reliable again. Switching back to eye movement."


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Signal:
    """Stands in for signal/run.py: sends reliability continuously and applies degrade controls."""

    def __init__(self, ws) -> None:
        self.ws = ws
        self.gain = {"eog_h": 1.0, "eog_v": 1.0, "blink": 1.0}
        self.pending: list[list] = []  # [readings left, signal, factor]

    async def run(self) -> None:
        async def controls() -> None:
            async for raw in self.ws:
                msg = json.loads(raw)
                if msg.get("type") == "degrade":
                    self.pending.append([LAG.get(msg["signal"], 0), msg["signal"], msg["factor"]])

        task = asyncio.create_task(controls())
        try:
            while True:
                for p in self.pending:
                    if p[0] == 0:
                        self.gain[p[1]] = p[2]
                    p[0] -= 1
                self.pending = [p for p in self.pending if p[0] >= 0]
                signals = {s: round(0.92 * g, 3) for s, g in self.gain.items()}
                await self.ws.send(json.dumps({"type": "reliability", "signals": signals, "ts": now()}))
                await asyncio.sleep(1 / RELIABILITY_HZ)
        finally:
            task.cancel()

    async def gesture(self, source: str, gesture: str) -> None:
        msg = {"type": "gesture", "source": source, "gesture": gesture, "confidence": 0.9, "ts": now()}
        await self.ws.send(json.dumps(msg))


class Listener:
    """Collects every event on one socket so steps can wait for a matching one."""

    def __init__(self, ws) -> None:
        self.ws, self.events, self._new = ws, [], asyncio.Event()

    async def run(self) -> None:
        async for raw in self.ws:
            self.events.append(json.loads(raw))
            self._new.set()

    async def wait_for(self, pred, timeout: float, since: int = 0) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            for ev in self.events[since:]:
                if pred(ev):
                    return ev
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            self._new.clear()
            try:
                await asyncio.wait_for(self._new.wait(), remaining)
            except asyncio.TimeoutError:
                pass


def now() -> int:
    return int(time.time() * 1000)


results: list[tuple[str, bool, str]] = []


async def step(name: str, coro) -> None:
    try:
        detail = await coro
        results.append((name, True, detail or ""))
    except Exception as e:  # noqa: BLE001 — report every failure, keep going
        results.append((name, False, f"{type(e).__name__}: {e}"))


async def main(base: str) -> None:
    ws_base = base.replace("http", "ws")
    async with httpx.AsyncClient(base_url=base, timeout=5) as http:
        token = (await http.post("/auth/login", json={"email": "caregiver@example.com", "password": PASSWORD})).json()["token"]

        async with (
            websockets.connect(f"{ws_base}/ws/signal?patient_id={PATIENT}") as sig_ws,
            websockets.connect(f"{ws_base}/ws/patient/{PATIENT}") as pat_ws,
            websockets.connect(f"{ws_base}/ws/caregiver/{PATIENT}?token={token}") as cg_ws,
        ):
            signal, patient, caregiver = Signal(sig_ws), Listener(pat_ws), Listener(cg_ws)
            tasks = [asyncio.create_task(t.run()) for t in (signal, patient, caregiver)]

            async def step1() -> str:
                await patient.wait_for(lambda e: e["type"] == "reliability" and e["mode"] == "wheel", 5)
                mark = len(patient.events)
                await signal.gesture("eog_h", "look_left")
                await signal.gesture("eog_h", "look_right")
                for cmd in ("LEFT", "RIGHT"):
                    await patient.wait_for(lambda e, c=cmd: e["type"] == "command" and e["command"] == c, 3, mark)
                # The patient screen speaks after SELECT and reports it.
                await pat_ws.send(json.dumps({"type": "spoken", "text": "I need water", "ts": now()}))
                await caregiver.wait_for(lambda e: e["type"] == "spoken" and e["text"] == "I need water", 3)
                return "look left/right → LEFT/RIGHT; spoken phrase reached caregiver"

            async def step2() -> str:
                mark = len(patient.events)
                r = await http.post("/demo/degrade", json={"signal": "eye", "factor": 0.3})
                r.raise_for_status()
                change = await patient.wait_for(lambda e: e["type"] == "mode_change" and e["to"] == "scan", 10, mark)
                snap = await patient.wait_for(lambda e: e["type"] == "reliability" and e["mode"] == "scan", 5, mark)
                assert snap["mapping"].get("SELECT") == "blink_double", snap["mapping"]
                mark = len(patient.events)
                await signal.gesture("eog_h", "look_left")  # degraded signal: must be ignored
                await signal.gesture("blink", "blink_double")
                cmd = await patient.wait_for(lambda e: e["type"] == "command", 3, mark)
                assert cmd["command"] == "SELECT", cmd
                await caregiver.wait_for(lambda e: e["type"] == "mode_change" and e["to"] == "scan", 3)
                return f"remapped to scan, double blink = SELECT. Banner: “{change['reason']}”"

            async def step3() -> str:
                mark = len(caregiver.events)
                # HELP is a wheel slot confirmed with SELECT; the patient screen then sends the alert.
                await pat_ws.send(json.dumps({"type": "alert", "message": "HELP", "ts": now()}))
                await caregiver.wait_for(lambda e: e["type"] == "alert" and e["message"] == "HELP", 3, mark)
                history = (await http.get(f"/patients/{PATIENT}/messages", headers={"Authorization": f"Bearer {token}"})).json()
                assert any(m["type"] == "alert" for m in history), "alert not in history"
                return "HELP slot → HELP alert on caregiver + saved to history"

            async def recover() -> str:
                mark = len(patient.events)
                await http.post("/demo/degrade", json={"signal": "eye", "factor": 1.0})
                change = await patient.wait_for(lambda e: e["type"] == "mode_change" and e["to"] == "wheel", 10, mark)
                return f"restored → wheel. “{change['reason']}”"

            await step("1. Select a phrase with eye movement", step1())
            await step("2. Eyes decline → double-blink scan mode", step2())
            await step("3. HELP reaches the caregiver", step3())
            await step("   Restore (reset for the next run)", recover())

            for t in tasks:
                t.cancel()

        r = await http.post("/predict", json={"patient_id": PATIENT, "recent_messages": ["I need water"]})
        phrases = r.json().get("phrases", [])
        results.append(("   Prediction returns phrases", 3 <= len(phrases) <= 5, ", ".join(phrases)))


if __name__ == "__main__":
    port = free_port()
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{tempfile.mkdtemp()}/demo_check.db",
        "DEMO_CAREGIVER_PASSWORD": PASSWORD,
    }
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--log-level", "warning"],
        cwd=ROOT / "backend",
        env=env,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                if httpx.get(f"{base}/health", timeout=0.5).status_code == 200:
                    break
            except httpx.TransportError:
                time.sleep(0.2)
        else:
            sys.exit("backend did not start")
        asyncio.run(main(base))
    finally:
        server.terminate()
        server.wait()

    print()
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"\n      {detail}" if detail else ""))
    failed = [r for r in results if not r[1]]
    print(f"\n{'DEMO READY' if not failed else f'{len(failed)} STEP(S) FAILED'}")
    sys.exit(1 if failed else 0)
