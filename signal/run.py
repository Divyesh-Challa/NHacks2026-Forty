"""Signal service entry point.

  python run.py --source synthetic                  # scripted gestures + keyboard
  python run.py --source synthetic --script none    # keyboard only: type l/r/b/j/h + Enter
  python run.py --source synthetic --detectors real # synthetic waveforms through the real filters/detectors
  python run.py --source arduino --port /dev/tty.usbmodem1101
"""

import argparse
import asyncio
import json
import logging
import sys
import threading

import websockets

from config import BACKEND_WS_URL

log = logging.getLogger("relay.signal")


def make_source(args: argparse.Namespace):
    if args.source == "synthetic":
        from sources.synthetic import DEFAULT_SCRIPT

        script = None if args.script == "none" else DEFAULT_SCRIPT
        if args.detectors == "real":
            from sources.pipeline import PipelineSource
            from tools.streams import SyntheticStream

            # Real waveforms take ~1 s per gesture, so space scripted ones further apart.
            return PipelineSource(SyntheticStream(), script=script, interval_s=args.interval or 2.0)
        from sources.synthetic import SyntheticSource

        return SyntheticSource(interval_s=args.interval or 0.6, script=script)
    from sources.arduino_serial import ArduinoSource

    return ArduinoSource(args.port)


async def listen_controls(ws, source) -> None:
    """Backend -> signal control messages (e.g. demo degrade)."""
    async for raw in ws:
        msg = json.loads(raw)
        if msg.get("type") == "degrade":
            log.info("degrade %s x%.2f", msg["signal"], msg["factor"])
            source.degrade(msg["signal"], msg["factor"])


KEYS = {"l": "look_left", "r": "look_right", "b": "blink_double", "j": "jaw_clench", "h": "jaw_hold"}


def read_keyboard(source, loop: asyncio.AbstractEventLoop) -> None:
    """Terminal gesture triggers for the synthetic source (runs in a thread)."""
    print("keys: l=look left  r=look right  b=double blink  j=jaw clench  h=jaw hold (HELP)  + Enter")
    for line in sys.stdin:
        for ch in line.strip().lower():
            if ch in KEYS:
                loop.call_soon_threadsafe(source.trigger, KEYS[ch])


async def main(args: argparse.Namespace) -> None:
    source = make_source(args)
    if hasattr(source, "trigger") and sys.stdin.isatty():
        threading.Thread(target=read_keyboard, args=(source, asyncio.get_running_loop()), daemon=True).start()
    url = f"{args.url}?patient_id={args.patient}"
    while True:
        try:
            async with websockets.connect(url) as ws:
                log.info("connected %s", url)
                controls = asyncio.create_task(listen_controls(ws, source))
                async for ev in source.events():
                    await ws.send(json.dumps(ev))
                    log.debug("sent %s", ev)
                    if ev["type"] == "gesture":
                        log.info("gesture %-12s %.2f", ev["gesture"], ev["confidence"])
                controls.cancel()
                return
        except (OSError, websockets.ConnectionClosed) as e:
            log.warning("backend unavailable (%s); retrying in 2 s", e)
            await asyncio.sleep(2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    p = argparse.ArgumentParser()
    p.add_argument("--source", choices=["synthetic", "arduino"], default="synthetic")
    p.add_argument("--port", default=None)
    p.add_argument("--patient", default="p1")
    p.add_argument("--url", default=BACKEND_WS_URL)
    p.add_argument("--interval", type=float, default=None, help="synthetic: seconds between scripted gestures (0.6 simulated, 2.0 real)")
    p.add_argument("--detectors", choices=["simulated", "real"], default="simulated", help="synthetic: simulated detector (demo default) or real filters/detectors")
    p.add_argument("--script", choices=["cycle", "none"], default="cycle", help="synthetic: scripted gestures or keyboard only")
    asyncio.run(main(p.parse_args()))
