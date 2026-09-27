"""The real ``Clock`` implementation.

This is the only place in the source tree that reads the wall clock or sleeps for real. Every
other module takes a ``Clock`` so it can be handed a fake in tests (see ``tests/fakes/clock.py``).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime


class SystemClock:
    """A ``Clock`` backed by the operating system clock.

    ``now`` uses the wall clock (for timestamps), ``monotonic`` uses ``time.monotonic`` (for
    durations, so it is immune to the wall clock being stepped by NTP), and ``sleep`` really
    blocks. Production uses this; tests never do.
    """

    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError(f"sleep seconds must be non-negative, got {seconds}")
        time.sleep(seconds)


__all__ = ["SystemClock"]
