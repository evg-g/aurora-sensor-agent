"""The higher-layer faults: the ones above the I²C wire.

``sim/faults.py`` covers chip/bus faults (bad CRC, NACK, timeout...). This module covers the three
faults from spec §7 that strike *after* a reading is decoded — in the pipeline, the buffer, or the
clock:

- ``NAN``        — a decoded value comes out as NaN (a glitch that passed CRC by chance). Caught by
  ``logic.filter.is_valid_reading``; :func:`nan_reading` builds one for tests.
- ``DISK_FULL``  — the SD card is full, so a buffer write fails. :class:`FaultingBufferStore` wraps
  a real buffer and raises on ``append`` so the agent's handling (flag it, do not crash, do not lose
  what is already buffered) can be proven.
- ``CLOCK_JUMP`` — the device RTC is stepped by NTP. Modelled in tests via ``FakeClock.step_wall``;
  the excursion machine and the agent's skew detector must both survive it. See ADR 0003.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from enum import Enum

from aurora_sensor_agent.models import Reading
from aurora_sensor_agent.protocols import BufferStore


class PipelineFault(Enum):
    """A fault above the I²C bus, injected at the pipeline/buffer/clock seams."""

    NAN = "nan"
    DISK_FULL = "disk_full"
    CLOCK_JUMP = "clock_jump"


class DiskFullError(OSError):
    """Raised by :class:`FaultingBufferStore` to imitate a full disk on a buffer write."""


def nan_reading(measured_at: datetime | None = None) -> Reading:
    """A ``Reading`` whose temperature is NaN — the poisoned sample the filter must reject."""
    when = measured_at if measured_at is not None else datetime(2026, 1, 1, tzinfo=UTC)
    return Reading(
        temperature_c=math.nan,
        humidity_pct=math.nan,
        measured_at=when,
        raw_temperature=0,
        raw_humidity=0,
    )


class FaultingBufferStore:
    """Wraps a ``BufferStore`` and fails ``append`` to imitate a full disk.

    ``fail_at`` is the append call index (0-based) at which to start failing. With ``fail_forever``
    the failure sticks (the disk stays full); otherwise it fires once and then the underlying store
    works again (a transient write error). All other operations pass straight through.
    """

    def __init__(self, inner: BufferStore, *, fail_at: int, fail_forever: bool = True) -> None:
        self._inner = inner
        self._fail_at = fail_at
        self._fail_forever = fail_forever
        self._appends = 0

    def append(self, reading_json: str) -> int:
        if self._fail_forever:
            should_fail = self._appends >= self._fail_at
        else:
            should_fail = self._appends == self._fail_at
        self._appends += 1
        if should_fail:
            raise DiskFullError("database or disk is full")
        return self._inner.append(reading_json)

    def pending(self, limit: int) -> list[tuple[int, str]]:
        return self._inner.pending(limit)

    def acknowledge(self, row_ids: list[int]) -> None:
        self._inner.acknowledge(row_ids)

    def depth(self) -> int:
        return self._inner.depth()


__all__ = ["DiskFullError", "FaultingBufferStore", "PipelineFault", "nan_reading"]
