"""Tests for the ``Reading`` value object."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from aurora_sensor_agent.models import Reading


def test_reading_accepts_aware_timestamp() -> None:
    reading = Reading(
        temperature_c=4.0,
        humidity_pct=45.0,
        measured_at=datetime(2026, 1, 1, tzinfo=UTC),
        raw_temperature=1000,
        raw_humidity=2000,
    )
    assert reading.temperature_c == 4.0


def test_reading_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Reading(
            temperature_c=4.0,
            humidity_pct=45.0,
            measured_at=datetime(2026, 1, 1),  # deliberately naive
            raw_temperature=1000,
            raw_humidity=2000,
        )
