"""The legacy UART probe: an ASCII, checksum-framed serial protocol.

The clinic's older fridges have a second temperature probe wired over a plain serial line. It speaks
a simple line protocol, NMEA-style::

    $T=4.12,H=45.3*3F\r\n
    │└──── body ────┘│└┴─ XOR checksum of the body, two hex digits, then CRLF
    └ start marker

Serial is messier than I²C: bytes arrive a few at a time, a line can be split across two reads, the
line can start mid-frame after a reconnect, and electrical noise inserts garbage. So the parsing is
split in two:

- :class:`FrameParser` — pure, clock-free, byte-oriented. You push whatever bytes arrived; it
  returns the complete, checksum-valid frame bodies it could extract, resynchronising past garbage
  and past a corrupt frame (counting the latter). All the framing edge cases are tested here.
- :class:`LegacyProbe` — wraps a ``SerialPort`` and a ``Clock`` and turns "read until you get a good
  reading, or the deadline passes" into a method. The I/O timing lives here, the logic does not.
"""

from __future__ import annotations

from dataclasses import dataclass

from aurora_sensor_agent.protocols import Clock, SerialPort

_START = ord("$")
_SEP = ord("*")
_TERM = b"\r\n"


class ProbeError(Exception):
    """Base class for legacy-probe failures."""


class ProbeTimeoutError(ProbeError):
    """No complete, valid frame arrived before the deadline."""


class ProbeFrameError(ProbeError):
    """A frame body was structurally invalid (missing fields, non-numeric)."""


@dataclass(frozen=True, slots=True)
class ProbeReading:
    """One reading from the legacy probe."""

    temperature_c: float
    humidity_pct: float


def checksum(body: bytes) -> int:
    """XOR of every byte in the body — the frame's integrity check."""
    result = 0
    for byte in body:
        result ^= byte
    return result


def encode_frame(temperature_c: float, humidity_pct: float) -> bytes:
    """Build a valid frame for ``(temperature_c, humidity_pct)`` — used by tests and simulators."""
    body = f"T={temperature_c:.2f},H={humidity_pct:.1f}".encode("ascii")
    return b"$" + body + b"*" + f"{checksum(body):02X}".encode("ascii") + _TERM


class FrameParser:
    """Extracts checksum-valid frame bodies from a byte stream. Pure, no clock, no I/O."""

    def __init__(self) -> None:
        self._buf = bytearray()
        self.checksum_errors = 0

    def push(self, data: bytes) -> list[bytes]:
        """Add received bytes; return every complete, valid frame body now available.

        Frames come back oldest first. The parser resynchronises past leading garbage and past a
        corrupt frame, counting checksum failures as it goes.
        """
        self._buf.extend(data)
        frames: list[bytes] = []
        while True:
            body = self._extract_one()
            if body is None:
                break
            frames.append(body)
        return frames

    def _extract_one(self) -> bytes | None:
        start = self._buf.find(_START)
        if start == -1:
            # No frame start in the buffer: it is all garbage. Keep nothing (resync).
            self._buf.clear()
            return None
        if start > 0:
            # Drop the garbage before the start marker.
            del self._buf[:start]
        sep = self._buf.find(_SEP)
        if sep == -1:
            return None  # body not finished yet
        # Need two checksum hex digits and the CRLF after '*'.
        if len(self._buf) < sep + 1 + 2 + len(_TERM):
            return None  # checksum/terminator not fully arrived yet
        body = bytes(self._buf[1:sep])
        checksum_hex = bytes(self._buf[sep + 1 : sep + 3])
        term = bytes(self._buf[sep + 3 : sep + 3 + len(_TERM)])
        frame_end = sep + 3 + len(_TERM)
        if term != _TERM:
            # Malformed tail: drop this start marker and resync from the next one.
            del self._buf[:1]
            self.checksum_errors += 1
            return self._extract_one()
        del self._buf[:frame_end]
        try:
            expected = int(checksum_hex, 16)
        except ValueError:
            self.checksum_errors += 1
            return self._extract_one()
        if expected != checksum(body):
            self.checksum_errors += 1
            return self._extract_one()
        return body


def parse_body(body: bytes) -> ProbeReading:
    """Parse a validated ``T=..,H=..`` body into a :class:`ProbeReading`."""
    fields: dict[str, float] = {}
    for part in body.split(b","):
        key, sep, value = part.partition(b"=")
        if not sep:
            raise ProbeFrameError(f"malformed field {part!r}")
        try:
            fields[key.decode("ascii")] = float(value)
        except ValueError as exc:
            raise ProbeFrameError(f"non-numeric field {part!r}") from exc
    if "T" not in fields or "H" not in fields:
        raise ProbeFrameError(f"missing T or H in body {body!r}")
    return ProbeReading(temperature_c=fields["T"], humidity_pct=fields["H"])


class LegacyProbe:
    """Reads ``ProbeReading``s from a ``SerialPort``, bounded by an injected ``Clock``."""

    def __init__(self, port: SerialPort, clock: Clock, *, chunk_size: int = 64) -> None:
        self._port = port
        self._clock = clock
        self._chunk = chunk_size
        self._parser = FrameParser()
        self._ready: list[bytes] = []

    @property
    def checksum_errors(self) -> int:
        return self._parser.checksum_errors

    def read_reading(self, timeout_s: float) -> ProbeReading:
        """Read until a valid frame arrives, or raise ``ProbeTimeoutError`` after ``timeout_s``.

        The port's own read timeout does the blocking; the clock only bounds the total wait, so this
        never busy-spins. Any already-buffered frame is returned before touching the port.
        """
        deadline = self._clock.monotonic() + timeout_s
        while True:
            if self._ready:
                return parse_body(self._ready.pop(0))
            if self._clock.monotonic() > deadline:
                raise ProbeTimeoutError(f"no valid frame within {timeout_s}s")
            chunk = self._port.read(self._chunk)
            if chunk:
                self._ready.extend(self._parser.push(chunk))
            elif self._clock.monotonic() > deadline:
                raise ProbeTimeoutError(f"no valid frame within {timeout_s}s")


__all__ = [
    "FrameParser",
    "LegacyProbe",
    "ProbeError",
    "ProbeFrameError",
    "ProbeReading",
    "ProbeTimeoutError",
    "checksum",
    "encode_frame",
    "parse_body",
]
