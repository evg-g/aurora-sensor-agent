"""A fake ``Clock`` for deterministic, instant tests.

This is a *fake*, not a mock: it is a real, working clock, just one whose time only moves when the
test tells it to. ``sleep`` does not block — it advances the fake's counters — so a test that waits
out an 8 ms sensor conversion runs in microseconds and always sees the same timestamps.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

_EPOCH = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)


class FakeClock:
    """A ``Clock`` whose time advances only on ``sleep``/``advance``."""

    def __init__(self, start: datetime | None = None, monotonic_start: float = 0.0) -> None:
        self._now = start if start is not None else _EPOCH
        if self._now.tzinfo is None:
            raise ValueError("FakeClock start must be timezone-aware")
        self._monotonic = monotonic_start

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return self._monotonic

    def sleep(self, seconds: float) -> None:
        self.advance(seconds)

    def advance(self, seconds: float) -> None:
        """Move time forward by ``seconds`` (both the wall clock and the monotonic counter)."""
        if seconds < 0:
            raise ValueError(f"cannot advance time backwards: {seconds}")
        self._monotonic += seconds
        self._now = self._now + timedelta(seconds=seconds)

    def step_wall(self, seconds: float) -> None:
        """Step the wall clock only, leaving the monotonic counter untouched.

        This models an NTP correction (or a manually set RTC): ``now`` jumps, ``monotonic`` does
        not. ``seconds`` may be negative to step the clock backwards. It is exactly the divergence
        the agent's clock-step detector looks for, and the backward-jump the excursion machine must
        survive.
        """
        self._now = self._now + timedelta(seconds=seconds)


__all__ = ["FakeClock"]
