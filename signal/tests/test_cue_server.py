"""The cue server over a real WebSocket: hello on connect, Start unblocks the recorder, cues reach the page."""

import json
import threading
import time

from websockets.sync.client import connect

from tools.cue_server import CueServer

PORT = 8799


def test_start_unblocks_and_cues_reach_the_page() -> None:
    srv = CueServer(port=PORT)
    time.sleep(0.5)  # server thread is starting
    with connect(f"ws://localhost:{PORT}") as ws:
        assert json.loads(ws.recv(timeout=3)) == {"type": "hello"}
        threading.Timer(0.2, lambda: ws.send(json.dumps({"type": "start"}))).start()
        srv.wait_for_start()  # returns only after the page's Start
        srv.send(type="cue", gesture="look_left", seconds=2.0, hold_s=1.2, index=1, total=40, next="look_up")
        msg = json.loads(ws.recv(timeout=3))
    assert msg["type"] == "cue" and msg["gesture"] == "look_left" and msg["next"] == "look_up"
