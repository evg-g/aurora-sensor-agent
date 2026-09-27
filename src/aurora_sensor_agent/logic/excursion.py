"""The cold-chain excursion state machine — the heart of the device.

Plain-language rule it enforces: the fridge temperature is allowed to leave its safe band briefly (a
nurse opens the door), but if it stays out for longer than ``dwell_minutes`` it is a real excursion
and must alarm. Once raised, it clears only after the temperature is back inside the band for
``recovery_minutes`` — so it does not flap on and off around the threshold.

Four states::

    NORMAL     in range, nothing wrong
    PENDING    out of range, but the dwell timer has not elapsed yet (could still be a door opening)
    EXCURSION  raised: out of range for longer than dwell
    CLEARING   back in range after an excursion, waiting out the recovery timer

The machine is *pure*: you feed it ``(temperature, at)`` pairs and it returns events. It never reads
a clock — the caller passes the timestamp of each reading. That is deliberate: ADR 0003 explains why
the excursion timer must not use the real wall clock (a fake clock is what lets a seven-day soak run
in milliseconds, and it is what lets the server re-derive the exact same excursions from the stored
series). Because the timing comes from the timestamps, a backward clock step cannot make a timer go
negative — the machine freezes its timeline on any sample whose timestamp went backwards.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum

from aurora_sensor_agent.config import ThresholdPolicy


class ExcursionState(Enum):
    """Where the machine currently is."""

    NORMAL = "normal"
    PENDING = "pending"
    EXCURSION = "excursion"
    CLEARING = "clearing"


class ExcursionDirection(Enum):
    """Which rail was breached."""

    LOW = "low"
    HIGH = "high"


class ExcursionEventKind(Enum):
    STARTED = "started"
    ENDED = "ended"


@dataclass(frozen=True, slots=True)
class Excursion:
    """One cold-chain breach.

    ``started_at`` is when the temperature first left the band (not when the dwell elapsed).
    ``ended_at`` is when it came back into the band (``None`` while still open).
    ``peak_temperature_c`` is the most extreme temperature reached — the highest for a HIGH breach,
    the lowest for a LOW one.
    """

    started_at: datetime
    direction: ExcursionDirection
    peak_temperature_c: float
    ended_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ExcursionEvent:
    """Emitted when an excursion is raised (STARTED) or cleared (ENDED)."""

    kind: ExcursionEventKind
    at: datetime
    excursion: Excursion


class ExcursionDetector:
    """Feeds on ``(temperature, at)`` and emits ``ExcursionEvent`` on raise/clear."""

    def __init__(self, policy: ThresholdPolicy) -> None:
        self._policy = policy
        self._dwell_s = policy.dwell_minutes * 60.0
        self._recovery_s = policy.recovery_minutes * 60.0
        self._state = ExcursionState.NORMAL
        self._last_at: datetime | None = None
        # Fields describing the breach currently being tracked (valid in any non-NORMAL state).
        self._breach_start_at: datetime | None = None
        self._recovery_start_at: datetime | None = None
        self._direction: ExcursionDirection | None = None
        self._peak_c: float = 0.0

    @property
    def state(self) -> ExcursionState:
        return self._state

    def _out_of_range(self, temperature_c: float) -> ExcursionDirection | None:
        if temperature_c < self._policy.min_temperature_c:
            return ExcursionDirection.LOW
        if temperature_c > self._policy.max_temperature_c:
            return ExcursionDirection.HIGH
        return None

    def _track_peak(self, temperature_c: float) -> None:
        """Keep the most extreme temperature seen during this breach."""
        if self._direction is ExcursionDirection.HIGH:
            self._peak_c = max(self._peak_c, temperature_c)
        else:
            self._peak_c = min(self._peak_c, temperature_c)

    def open_excursion(self) -> Excursion:
        """The excursion currently being tracked, as an open (``ended_at is None``) record."""
        assert self._breach_start_at is not None and self._direction is not None
        return Excursion(
            started_at=self._breach_start_at,
            direction=self._direction,
            peak_temperature_c=self._peak_c,
        )

    def update(self, temperature_c: float, at: datetime) -> ExcursionEvent | None:
        """Process one reading. Returns a STARTED/ENDED event, or ``None`` if nothing changed."""
        # Guard against a backward clock step: never let a timer measure negative time. We freeze
        # the timeline at the last seen timestamp so this sample counts, but advances no timer.
        if self._last_at is not None and at < self._last_at:
            at = self._last_at
        self._last_at = at

        direction = self._out_of_range(temperature_c)

        if self._state is ExcursionState.NORMAL:
            if direction is not None:
                self._state = ExcursionState.PENDING
                self._breach_start_at = at
                self._direction = direction
                self._peak_c = temperature_c
            return None

        if self._state is ExcursionState.PENDING:
            if direction is None:
                # Back in range before dwell elapsed: a door opening, not an excursion.
                self._reset_to_normal()
                return None
            self._track_peak(temperature_c)
            assert self._breach_start_at is not None
            if (at - self._breach_start_at).total_seconds() >= self._dwell_s:
                self._state = ExcursionState.EXCURSION
                return ExcursionEvent(ExcursionEventKind.STARTED, at, self.open_excursion())
            return None

        if self._state is ExcursionState.EXCURSION:
            if direction is not None:
                self._track_peak(temperature_c)
            else:
                self._state = ExcursionState.CLEARING
                self._recovery_start_at = at
            return None

        # CLEARING
        if direction is not None:
            # Dropped back out of range before recovery finished: still the same excursion.
            self._track_peak(temperature_c)
            self._state = ExcursionState.EXCURSION
            self._recovery_start_at = None
            return None
        assert self._recovery_start_at is not None
        if (at - self._recovery_start_at).total_seconds() >= self._recovery_s:
            ended = replace(self.open_excursion(), ended_at=self._recovery_start_at)
            self._reset_to_normal()
            return ExcursionEvent(ExcursionEventKind.ENDED, at, ended)
        return None

    def _reset_to_normal(self) -> None:
        self._state = ExcursionState.NORMAL
        self._breach_start_at = None
        self._recovery_start_at = None
        self._direction = None
        self._peak_c = 0.0


def detect_excursions(
    series: list[tuple[datetime, float]], policy: ThresholdPolicy
) -> list[Excursion]:
    """Run a fresh detector over a whole ``(at, temperature)`` series.

    Returns every excursion found, closed ones first and an open one last if the series ends
    mid-breach (its ``ended_at`` is ``None``). This is the function a shared fixture set drives, so
    the device and the server (milestone 10) can be proved to agree.
    """
    detector = ExcursionDetector(policy)
    excursions: list[Excursion] = []
    for at, temperature in series:
        event = detector.update(temperature, at)
        # A closed excursion carries its full span; the STARTED event needs no separate handling.
        if event is not None and event.kind is ExcursionEventKind.ENDED:
            excursions.append(event.excursion)
    # If the series ends while an excursion is raised (or clearing), surface it as still-open.
    if detector.state in (ExcursionState.EXCURSION, ExcursionState.CLEARING):
        excursions.append(detector.open_excursion())
    return excursions


__all__ = [
    "Excursion",
    "ExcursionDetector",
    "ExcursionDirection",
    "ExcursionEvent",
    "ExcursionEventKind",
    "ExcursionState",
    "detect_excursions",
]
