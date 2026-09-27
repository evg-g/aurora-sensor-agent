"""Tests for exponential backoff with jitter."""

from __future__ import annotations

import random

import pytest
from hypothesis import given
from hypothesis import strategies as st

from aurora_sensor_agent.logic.backoff import Backoff, compute_delay


def test_no_jitter_grows_exponentially_then_caps() -> None:
    rng = random.Random(0)
    delays = [
        compute_delay(n, base_seconds=1.0, factor=2.0, max_seconds=10.0, jitter=False, rng=rng)
        for n in range(6)
    ]
    assert delays == [1.0, 2.0, 4.0, 8.0, 10.0, 10.0]  # 16 and 32 are capped at 10


def test_full_jitter_stays_within_the_cap() -> None:
    rng = random.Random(1234)
    for attempt in range(8):
        cap = min(30.0, 1.0 * 2.0**attempt)
        delay = compute_delay(
            attempt, base_seconds=1.0, factor=2.0, max_seconds=30.0, jitter=True, rng=rng
        )
        assert 0.0 <= delay <= cap


def test_jitter_is_deterministic_for_a_seed() -> None:
    def run() -> list[float]:
        rng = random.Random(7)
        return [
            compute_delay(n, base_seconds=1.0, factor=2.0, max_seconds=60.0, jitter=True, rng=rng)
            for n in range(5)
        ]

    assert run() == run()


def test_negative_attempt_is_rejected() -> None:
    with pytest.raises(ValueError, match="attempt must be"):
        compute_delay(
            -1, base_seconds=1.0, factor=2.0, max_seconds=10.0, jitter=False, rng=random.Random()
        )


def test_stateful_backoff_advances_and_resets() -> None:
    backoff = Backoff(base_seconds=1.0, factor=2.0, max_seconds=100.0, jitter=False)
    assert backoff.next_delay() == 1.0
    assert backoff.next_delay() == 2.0
    assert backoff.next_delay() == 4.0
    backoff.reset()
    assert backoff.attempt == 0
    assert backoff.next_delay() == 1.0


@given(st.integers(min_value=0, max_value=40))
def test_delay_never_exceeds_cap(attempt: int) -> None:
    delay = compute_delay(
        attempt,
        base_seconds=0.5,
        factor=2.0,
        max_seconds=45.0,
        jitter=True,
        rng=random.Random(attempt),
    )
    assert 0.0 <= delay <= 45.0
