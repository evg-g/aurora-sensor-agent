"""Tests for the real ``SystemClock``. Kept fast: the only sleep is zero seconds."""

from __future__ import annotations

from datetime import UTC

import pytest

from aurora_sensor_agent.clock import SystemClock


def test_now_is_timezone_aware_utc() -> None:
    now = SystemClock().now()
    assert now.tzinfo is not None
    assert now.utcoffset() == UTC.utcoffset(None)


def test_monotonic_never_goes_backwards() -> None:
    clock = SystemClock()
    first = clock.monotonic()
    second = clock.monotonic()
    assert second >= first


def test_sleep_zero_returns_immediately() -> None:
    SystemClock().sleep(0)  # must not raise


def test_sleep_rejects_negative_duration() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        SystemClock().sleep(-0.5)
