"""Tests for signal conditioning: the NaN guard, calibration, and the median filter."""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

from aurora_sensor_agent.logic.filter import MedianFilter, calibrate, is_valid_reading
from aurora_sensor_agent.models import Reading

_AT = datetime(2026, 1, 1, tzinfo=UTC)


def _reading(temperature_c: float, humidity_pct: float = 45.0) -> Reading:
    return Reading(
        temperature_c=temperature_c,
        humidity_pct=humidity_pct,
        measured_at=_AT,
        raw_temperature=0,
        raw_humidity=0,
    )


def test_valid_reading_accepts_a_normal_sample() -> None:
    assert is_valid_reading(_reading(4.0)) is True


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_valid_reading_rejects_non_finite_temperature(bad: float) -> None:
    assert is_valid_reading(_reading(bad)) is False


def test_valid_reading_rejects_out_of_physical_range() -> None:
    assert is_valid_reading(_reading(200.0)) is False
    assert is_valid_reading(_reading(4.0, humidity_pct=150.0)) is False


def test_calibrate_adds_offset_to_temperature_only() -> None:
    calibrated = calibrate(_reading(4.0, humidity_pct=45.0), 0.5)
    assert calibrated.temperature_c == pytest.approx(4.5)
    assert calibrated.humidity_pct == pytest.approx(45.0)


def test_median_ignores_a_single_outlier() -> None:
    filt = MedianFilter(window=5)
    for value in (4.0, 4.1, 4.0, 4.2):
        filt.push(value)
    # One wild spike does not move the median.
    assert filt.push(80.0) == pytest.approx(4.1)


def test_median_window_of_one_is_passthrough() -> None:
    filt = MedianFilter(window=1)
    assert filt.push(7.3) == pytest.approx(7.3)
    assert filt.push(-2.0) == pytest.approx(-2.0)


def test_median_rejects_non_finite() -> None:
    filt = MedianFilter(window=3)
    with pytest.raises(ValueError, match="non-finite"):
        filt.push(math.nan)


def test_zero_window_is_rejected() -> None:
    with pytest.raises(ValueError, match="window must be"):
        MedianFilter(window=0)


def test_reset_clears_the_window() -> None:
    filt = MedianFilter(window=3)
    filt.push(10.0)
    filt.push(20.0)
    filt.reset()
    # After reset the first value is the median again (no memory of 10/20).
    assert filt.push(4.0) == pytest.approx(4.0)


@given(st.lists(st.floats(min_value=-40, max_value=80), min_size=1, max_size=20))
def test_median_is_within_range_of_inputs(values: list[float]) -> None:
    # Property: a median is always between the smallest and largest value seen in the window.
    filt = MedianFilter(window=len(values))
    result = 0.0
    for value in values:
        result = filt.push(value)
    assert min(values) <= result <= max(values)
