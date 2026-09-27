"""Tests for the excursion state machine — the device's most important logic.

Two layers here: hand-written tests that pin each rule of the state machine (dwell, recovery, short
spike, flapping, the backward-clock guard), and a data-driven test that runs the *shared* fixture
set in ``tests/fixtures/excursions/cases.json`` through :func:`detect_excursions`. That fixture set
is the contract the server engine (milestone 10) will be held to as well, so the two implementations
can be proved to agree.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from aurora_sensor_agent.config import ThresholdPolicy
from aurora_sensor_agent.logic.excursion import (
    ExcursionDetector,
    ExcursionDirection,
    ExcursionEventKind,
    ExcursionState,
    detect_excursions,
)

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
_FIXTURES = Path(__file__).parents[2] / "fixtures" / "excursions" / "cases.json"


def _at(offset_s: float) -> datetime:
    return _EPOCH + timedelta(seconds=offset_s)


def _policy() -> ThresholdPolicy:
    return ThresholdPolicy(
        min_temperature_c=2.0, max_temperature_c=8.0, dwell_minutes=15.0, recovery_minutes=10.0
    )


def _feed(detector: ExcursionDetector, series: list[tuple[float, float]]) -> list[str]:
    """Feed ``(offset_seconds, temperature)`` pairs; return the kind of each emitted event."""
    kinds: list[str] = []
    for offset, temperature in series:
        event = detector.update(temperature, _at(offset))
        if event is not None:
            kinds.append(event.kind.value)
    return kinds


def _state(detector: ExcursionDetector) -> ExcursionState:
    """Read the state through a function so mypy does not narrow it across ``update`` calls."""
    return detector.state


def test_in_range_never_raises() -> None:
    detector = ExcursionDetector(_policy())
    kinds = _feed(detector, [(i * 300, 5.0) for i in range(10)])
    assert kinds == []
    assert _state(detector) is ExcursionState.NORMAL


def test_short_spike_below_dwell_does_not_alert() -> None:
    # Out of range for 600 s, dwell is 900 s: a door opening, not an excursion.
    detector = ExcursionDetector(_policy())
    kinds = _feed(detector, [(0, 5.0), (300, 10.0), (600, 10.0), (900, 5.0)])
    assert kinds == []
    assert _state(detector) is ExcursionState.NORMAL


def test_sustained_breach_raises_after_dwell() -> None:
    detector = ExcursionDetector(_policy())
    # Out from t=0; dwell 900 s is reached exactly at t=900.
    events = [detector.update(10.0, _at(t)) for t in (0, 300, 600, 900)]
    assert [e for e in events[:3] if e is not None] == []
    raised = events[3]
    assert raised is not None
    assert raised.kind is ExcursionEventKind.STARTED
    assert raised.excursion.started_at == _at(0)
    assert raised.excursion.direction is ExcursionDirection.HIGH


def test_excursion_clears_only_after_recovery() -> None:
    detector = ExcursionDetector(_policy())
    _feed(detector, [(0, 10.0), (300, 10.0), (600, 10.0), (900, 10.0)])  # raised at 900
    assert _state(detector) is ExcursionState.EXCURSION
    # Back in range at 1200; recovery is 600 s, so it clears at 1800, not before.
    assert detector.update(5.0, _at(1200)) is None  # -> CLEARING
    assert detector.update(5.0, _at(1500)) is None  # 300 s < 600 s
    cleared = detector.update(5.0, _at(1800))  # 600 s >= 600 s
    assert cleared is not None
    assert cleared.kind is ExcursionEventKind.ENDED
    assert cleared.excursion.ended_at == _at(1200)  # ended when it first came back in range
    assert _state(detector) is ExcursionState.NORMAL


def test_return_to_range_before_recovery_keeps_one_excursion() -> None:
    detector = ExcursionDetector(_policy())
    kinds = _feed(
        detector,
        [
            (0, 10.0),
            (300, 10.0),
            (600, 10.0),
            (900, 10.0),  # raised
            (1200, 5.0),  # clearing
            (1500, 10.0),  # back out before recovery -> same excursion
            (1800, 10.0),
            (2100, 5.0),
            (2400, 5.0),
            (2700, 5.0),  # clears at 2700 (recovery from 2100)
        ],
    )
    assert kinds == ["started", "ended"]


def test_peak_tracks_the_most_extreme_value() -> None:
    detector = ExcursionDetector(_policy())
    detector.update(9.0, _at(0))
    detector.update(12.0, _at(300))
    detector.update(10.0, _at(600))
    raised = detector.update(11.0, _at(900))
    assert raised is not None
    assert raised.excursion.peak_temperature_c == 12.0


def test_backward_clock_step_does_not_prematurely_clear() -> None:
    # An excursion is raised, then the wall clock jumps backwards. The recovery timer must not be
    # tricked into thinking the required time has elapsed, and no spurious event is emitted.
    detector = ExcursionDetector(_policy())
    _feed(detector, [(0, 10.0), (300, 10.0), (600, 10.0), (900, 10.0)])  # raised
    assert _state(detector) is ExcursionState.EXCURSION
    detector.update(5.0, _at(1000))  # -> CLEARING at 1000
    # Clock jumps back to before the recovery start; timeline is frozen, timer cannot go negative.
    assert detector.update(5.0, _at(200)) is None
    assert _state(detector) is ExcursionState.CLEARING


@dataclass(frozen=True)
class _ExpectedExcursion:
    started_offset: float
    ended_offset: float | None
    direction: str
    peak_temperature_c: float


@dataclass(frozen=True)
class _Case:
    name: str
    series: list[tuple[float, float]]
    expected: list[_ExpectedExcursion]


def _load_fixture_cases() -> list[_Case]:
    data = json.loads(_FIXTURES.read_text(encoding="utf-8"))
    cases: list[_Case] = []
    for raw in data["cases"]:
        series = [(float(offset), float(temp)) for offset, temp in raw["series"]]
        expected = [
            _ExpectedExcursion(
                started_offset=float(item["started_offset"]),
                ended_offset=None if item["ended_offset"] is None else float(item["ended_offset"]),
                direction=str(item["direction"]),
                peak_temperature_c=float(item["peak_temperature_c"]),
            )
            for item in raw["expected"]
        ]
        cases.append(_Case(name=str(raw["name"]), series=series, expected=expected))
    return cases


@pytest.mark.parametrize("case", _load_fixture_cases(), ids=lambda c: c.name)
def test_shared_fixture_cases(case: _Case) -> None:
    series = [(_at(offset), temp) for offset, temp in case.series]
    excursions = detect_excursions(series, _policy())

    assert len(excursions) == len(case.expected), case.name
    for got, want in zip(excursions, case.expected, strict=True):
        assert got.started_at == _at(want.started_offset)
        assert got.direction.value == want.direction
        assert got.peak_temperature_c == pytest.approx(want.peak_temperature_c)
        if want.ended_offset is None:
            assert got.ended_at is None
        else:
            assert got.ended_at == _at(want.ended_offset)
