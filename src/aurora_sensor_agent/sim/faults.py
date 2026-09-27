"""The chip-level fault catalogue the simulator can inject.

These are the failures a real I²C sensor throws at you on a bad day. Each one is injected at a
chosen measurement index so a test can say "corrupt the 3rd reading" and prove the driver reacts
correctly (rejects it, retries, flags it) without ever touching hardware.

Faults split by *when* they strike in the write→read exchange:

- write-time (the command never lands): ``NACK``, ``POWER_LOSS``
- read-time (the data comes back wrong): ``BAD_CRC``, ``TIMEOUT``, ``SHORT_READ``, ``STUCK``

Most faults are one-shot (a transient glitch): they fire once at their index and then clear, so a
retry succeeds — that is what lets backoff/recovery be tested. ``STUCK`` is the exception: once it
fires the sensor freezes on its last value and stays that way, which is how a wedged sensor behaves.

The higher-layer faults from the full catalogue in §7 (NaN in the pipeline, disk full in the
buffer, clock jump) are not bus faults; they are injected at the buffer/clock seams in milestone 9.
"""

from __future__ import annotations

from enum import Enum


class Sht4xFault(Enum):
    """A single injectable sensor/bus fault."""

    NACK = "nack"
    """Device does not acknowledge the command write → ``OSError`` (no data produced)."""

    POWER_LOSS = "power_loss"
    """Power lost mid-write → ``OSError`` and the bus goes dead until reopened."""

    BAD_CRC = "bad_crc"
    """A data byte's CRC is corrupted → the driver must raise ``CrcError`` and drop the reading."""

    TIMEOUT = "timeout"
    """The read never completes → ``TimeoutError``."""

    SHORT_READ = "short_read"
    """Fewer bytes come back than requested → the driver must reject the frame."""

    STUCK = "stuck"
    """The sensor freezes on its last value and returns it for every subsequent read."""


WRITE_FAULTS = frozenset({Sht4xFault.NACK, Sht4xFault.POWER_LOSS})
READ_FAULTS = frozenset(
    {Sht4xFault.BAD_CRC, Sht4xFault.TIMEOUT, Sht4xFault.SHORT_READ, Sht4xFault.STUCK}
)


__all__ = ["READ_FAULTS", "WRITE_FAULTS", "Sht4xFault"]
