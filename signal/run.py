"""Signal service entry point.

  python run.py --source synthetic
  python run.py --source arduino --port /dev/tty.usbmodem1101
"""

import argparse
import asyncio
import json
import logging

import websockets

from config import BACKEND_WS_URL

log = logging.getLogger("relay.signal")


def make_source(args: argparse.Namespace):
    if args.source == "synthetic":
        from sources.synthetic import SyntheticSource

        return SyntheticSource(interval_s=args.interval)
    from sources.arduino_serial import ArduinoSource

    return ArduinoSource(args.port)


async def listen_controls(ws, source) -> None:
    """Backend -> signal control messages (e.g. demo degrade)."""
    async for raw in ws:
        msg = json.loads(raw)
        if msg.get("type") == "degrade":
            log.info("degrade %s x%.2f", msg["signal"], msg["factor"])
            source.degrade(msg["signal"], msg["factor"])


async def main(args: argparse.Namespace) -> None:
    source = make_source(args)
    url = f"{args.url}?patient_id={args.patient}"
    while True:
        try:
            async with websockets.connect(url) as ws:
                log.info("connected %s", url)
                controls = asyncio.create_task(listen_controls(ws, source))
                async for ev in source.events():
                    await ws.send(json.dumps(ev))
                    log.info("sent %s", ev)
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
    p.add_argument("--interval", type=float, default=2.0, help="synthetic: seconds between gestures")
    asyncio.run(main(p.parse_args()))
