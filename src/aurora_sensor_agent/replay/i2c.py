"""An ``I2CBus`` that replays a recorded trace of command/response frames.

The trace is a ``.jsonl`` file, one exchange per line::

    {"command": "0xFD", "response": "6a0e...  (12 hex chars = 6 bytes)"}

On each ``write`` the bus remembers the command; on the next ``read`` it returns the recorded
response for the next exchange in order. If the driver sends a different command than the one
recorded, that is drift — the bus raises, so a change in the driver's command sequence is caught
instead of silently replaying stale bytes.

Because the bytes are fixed, replay is deterministic no matter what clock or machine runs it, which
is exactly what a regression fixture needs.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ReplayFrame:
    """One recorded I²C exchange: the command byte written, and the bytes read back."""

    command: int
    response: bytes


class ReplayExhaustedError(OSError):
    """Raised when the driver reads past the end of the recorded trace."""


class ReplayI2CBus:
    """Replays recorded ``ReplayFrame`` exchanges in order."""

    def __init__(self, frames: Sequence[ReplayFrame]) -> None:
        self._frames = list(frames)
        self._index = 0
        self._pending_cmd: int | None = None

    @classmethod
    def from_jsonl(cls, path: str | Path) -> ReplayI2CBus:
        """Load a trace file written by ``scripts/record_trace.py``."""
        frames: list[ReplayFrame] = []
        text = Path(path).read_text(encoding="utf-8")
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            record = json.loads(line)
            try:
                command = int(record["command"], 16)
                response = bytes.fromhex(record["response"])
            except (KeyError, ValueError) as exc:
                raise ValueError(f"{path}:{line_number}: malformed trace record: {exc}") from exc
            frames.append(ReplayFrame(command=command, response=response))
        if not frames:
            raise ValueError(f"{path}: trace file has no frames")
        return cls(frames)

    def write(self, address: int, data: bytes) -> None:
        if len(data) != 1:
            raise OSError(f"replay expects single-byte commands, got {len(data)}")
        self._pending_cmd = data[0]

    def read(self, address: int, length: int) -> bytes:
        if self._index >= len(self._frames):
            raise ReplayExhaustedError("no more recorded frames to replay")
        frame = self._frames[self._index]
        if self._pending_cmd is not None and self._pending_cmd != frame.command:
            raise OSError(
                f"trace drift at frame {self._index}: recorded command "
                f"0x{frame.command:02X}, driver sent 0x{self._pending_cmd:02X}"
            )
        self._index += 1
        self._pending_cmd = None
        return frame.response[:length]

    def close(self) -> None:
        return None


__all__ = ["ReplayExhaustedError", "ReplayFrame", "ReplayI2CBus"]
