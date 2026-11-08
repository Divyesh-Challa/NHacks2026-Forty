"""Local WebSocket the /calibrate page connects to. The recorder sends each cue the instant it starts
labelling the data, so what the person sees and hears is exactly what the samples are labelled with.

Page -> server: {"type": "start"} (the Start click; also what unlocks browser audio).
Server -> page: hello | ready | intro | cue | rest | done  (see frontend/src/pages/Calibrate.tsx).
"""

import asyncio
import json
import threading

import websockets

PORT = 8765


class CueServer:
    def __init__(self, port: int = PORT) -> None:
        self.port = port
        self.clients: set = set()
        self.started = threading.Event()
        self.error: OSError | None = None
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)

        async def handler(ws) -> None:
            self.clients.add(ws)
            await ws.send(json.dumps({"type": "hello"}))
            try:
                async for raw in ws:
                    if json.loads(raw).get("type") == "start":
                        self.started.set()
            finally:
                self.clients.discard(ws)

        async def main() -> None:
            async with websockets.serve(handler, "localhost", self.port):
                await asyncio.Future()

        try:
            self.loop.run_until_complete(main())
        except OSError as e:  # port taken: say so instead of waiting forever for a Start that can't come
            self.error = e
            self.started.set()

    def send(self, **msg) -> None:
        data = json.dumps(msg)

        async def go() -> None:
            websockets.broadcast(self.clients, data)

        asyncio.run_coroutine_threadsafe(go(), self.loop)

    def wait_for_start(self) -> None:
        while not self.started.wait(0.5):  # short waits so Ctrl-C works
            pass
        if self.error:
            raise SystemExit(f"cue server could not listen on localhost:{self.port}: {self.error}")
