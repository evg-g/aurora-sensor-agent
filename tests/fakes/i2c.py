"""A scripted fake ``I2CBus`` for isolating the driver from any simulator.

It records every write and returns pre-loaded responses in order. That lets a driver test assert
exactly which command byte was sent and hand back a hand-built frame (including a deliberately
broken one) without any physics or timing in the way.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable


class ScriptedI2CBus:
    """Returns queued byte responses and records the commands written to it."""

    def __init__(self, responses: Iterable[bytes]) -> None:
        self.writes: list[tuple[int, bytes]] = []
        self._responses: deque[bytes] = deque(responses)
        self.closed = False

    def write(self, address: int, data: bytes) -> None:
        self.writes.append((address, bytes(data)))

    def read(self, address: int, length: int) -> bytes:
        if not self._responses:
            raise AssertionError("ScriptedI2CBus.read called with no scripted response left")
        # Return the scripted bytes verbatim so a test can supply a short frame on purpose.
        return self._responses.popleft()

    def close(self) -> None:
        self.closed = True


__all__ = ["ScriptedI2CBus"]
