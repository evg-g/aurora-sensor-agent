"""The hardware and I/O seams, defined as ``typing.Protocol``.

Every place the agent touches the outside world — the I²C sensor, the legacy serial probe, a
GPIO pin, the wall clock, the network transport, the local buffer — is described here as a
Protocol (a structural interface). Nothing in this file imports a hardware library.

Why bother: a Protocol is a promise about *shape*, not identity. Any class with matching methods
satisfies it, with no base class and no registration. That is what lets the same driver run
against real hardware, a simulator, or a recorded trace, and what lets the whole logic layer be
tested on a laptop with no hardware, no network, and no Docker (ADR 0001).

Which seams are exercised in milestone 8:

- ``I2CBus`` and ``Clock`` are implemented (``real``/``sim``/``replay`` buses, ``SystemClock``,
  and a ``FakeClock`` in the tests) and driven by the SHT4x driver.
- ``SerialPort`` (legacy probe), ``GpioPin`` (LED + buzzer), ``Transport`` (MQTT/HTTP), and
  ``BufferStore`` (SQLite store-and-forward) are defined now as the agreed contracts; their
  implementations land in milestones 9-11. Defining them here keeps the seams in one place.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class I2CBus(Protocol):
    """A minimal I²C master, enough to talk to the SHT4x.

    The SHT4x conversation is: write a one-byte command, wait the measurement time, then read a
    fixed number of bytes. That is all this seam needs to expose. ``address`` is the 7-bit I²C
    device address (the SHT4x default is ``0x44``).
    """

    def write(self, address: int, data: bytes) -> None:
        """Write ``data`` to the device at ``address``. Raises ``OSError`` on a bus error."""
        ...

    def read(self, address: int, length: int) -> bytes:
        """Read exactly ``length`` bytes from ``address``. Raises ``OSError`` on a bus error."""
        ...

    def close(self) -> None:
        """Release the bus. Safe to call more than once."""
        ...


@runtime_checkable
class SerialPort(Protocol):
    """A byte-oriented serial line for the legacy UART probe.

    Framing, partial reads, and timeouts are the caller's problem — this seam only moves bytes.
    Implemented in milestone 9 (``pyserial`` ``loop://`` and ``pty`` pairs in tests).
    """

    def write(self, data: bytes) -> int:
        """Write ``data`` and return the number of bytes written."""
        ...

    def read(self, size: int) -> bytes:
        """Read up to ``size`` bytes. May return fewer on a timeout, never more."""
        ...

    def close(self) -> None:
        """Close the port."""
        ...


@runtime_checkable
class GpioPin(Protocol):
    """A single digital output pin (status LED segment or buzzer).

    Implemented in milestone 9 against ``gpiozero``'s ``MockFactory`` in tests.
    """

    def high(self) -> None:
        """Drive the pin high (on)."""
        ...

    def low(self) -> None:
        """Drive the pin low (off)."""
        ...

    @property
    def is_active(self) -> bool:
        """True while the pin is driven high."""
        ...


@runtime_checkable
class Clock(Protocol):
    """Time, injected so tests never touch the real wall clock or sleep for real.

    ``now`` is timezone-aware UTC (for ``measured_at`` timestamps). ``monotonic`` is a steadily
    increasing seconds counter for durations and backoff — it never goes backwards. ``sleep``
    is how the driver waits out the sensor's measurement time; a fake clock advances ``monotonic``
    instead of blocking, which is what keeps time-dependent tests fast and deterministic.
    """

    def now(self) -> datetime:
        """Current time as an aware UTC ``datetime``."""
        ...

    def monotonic(self) -> float:
        """A monotonic seconds counter, unaffected by wall-clock changes."""
        ...

    def sleep(self, seconds: float) -> None:
        """Wait ``seconds``. A fake clock advances its monotonic counter instead of blocking."""
        ...


@runtime_checkable
class Transport(Protocol):
    """The uplink to the backend (MQTT primary, HTTP fallback).

    Defined here as the seam; the MQTT/HTTP implementations and at-least-once delivery land in
    milestones 10-11. ``publish`` carries an already-serialised payload for a topic/endpoint.
    """

    def publish(self, topic: str, payload: bytes) -> None:
        """Send ``payload`` to ``topic``. Raises on a delivery failure so the caller can retry."""
        ...

    def close(self) -> None:
        """Tear down the connection."""
        ...


@runtime_checkable
class BufferStore(Protocol):
    """The local store-and-forward buffer (SQLite on the device).

    Readings are appended while offline and drained once the uplink returns. Defined here as the
    seam; the SQLite implementation and the eviction policy land in milestone 9.
    """

    def append(self, reading_json: str) -> int:
        """Persist one serialised reading and return its buffer row id."""
        ...

    def pending(self, limit: int) -> list[tuple[int, str]]:
        """Return up to ``limit`` un-acknowledged ``(row_id, reading_json)`` rows, oldest first."""
        ...

    def acknowledge(self, row_ids: list[int]) -> None:
        """Drop rows the backend has confirmed, freeing space."""
        ...

    def depth(self) -> int:
        """Number of un-acknowledged rows currently buffered."""
        ...


__all__ = [
    "BufferStore",
    "Clock",
    "GpioPin",
    "I2CBus",
    "SerialPort",
    "Transport",
]
