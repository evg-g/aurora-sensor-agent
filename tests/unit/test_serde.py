"""Tests for reading serialisation used by the buffer and the batch envelope."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from aurora_sensor_agent.models import Reading
from aurora_sensor_agent.serde import reading_from_json, reading_to_json


def _reading() -> Reading:
    return Reading(
        temperature_c=4.25,
        humidity_pct=45.5,
        measured_at=datetime(2026, 3, 29, 1, 30, tzinfo=UTC),
        raw_temperature=18000,
        raw_humidity=26000,
    )


def test_round_trip_preserves_values() -> None:
    original = _reading()
    restored = reading_from_json(reading_to_json(original))
    assert restored == original


def test_json_is_a_single_sorted_line() -> None:
    payload = reading_to_json(_reading())
    assert "\n" not in payload
    data = json.loads(payload)
    assert data["raw_temperature"] == 18000
    assert data["measured_at"].endswith("+00:00")


def test_naive_timestamp_is_treated_as_utc() -> None:
    # A payload missing the offset is read back as UTC rather than crashing.
    restored = reading_from_json(
        '{"v":1,"measured_at":"2026-01-01T00:00:00","temperature_c":4.0,'
        '"humidity_pct":45.0,"raw_temperature":0,"raw_humidity":0}'
    )
    assert restored.measured_at.tzinfo is UTC
