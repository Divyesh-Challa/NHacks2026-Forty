"""Muse 2 via BrainFlow. Owner: Role B (Saturday).

TODO: confirm BrainFlow board ID for the kit's USB BLE dongle; use AF7/AF8 for blinks,
temporal/high-frequency content for jaw clench. Same events() interface as SyntheticSource.
"""


class MuseSource:
    def __init__(self, serial_port: str | None = None) -> None:
        self.serial_port = serial_port

    def degrade(self, signal: str, factor: float) -> None:
        raise NotImplementedError

    async def events(self):
        raise NotImplementedError
        yield  # pragma: no cover
