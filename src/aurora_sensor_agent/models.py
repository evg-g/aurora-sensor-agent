"""Value objects passed between the layers.

Kept tiny and immutable on purpose: a ``Reading`` is a fact ("at this instant the fridge was
this warm"), so it should not be mutated after it is created.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# SHT4x physical measurement ranges, from the datasheet. Used to sanity-check conversions.
TEMPERATURE_MIN_C = -45.0
TEMPERATURE_MAX_C = 130.0
HUMIDITY_MIN_PCT = 0.0
HUMIDITY_MAX_PCT = 100.0


@dataclass(frozen=True, slots=True)
class Reading:
    """One temperature + humidity sample from the sensor.

    ``raw_temperature`` / ``raw_humidity`` are the 16-bit values straight off the wire, kept so a
    reading can be re-converted or replayed byte-for-byte. ``measured_at`` is the device clock at
    the moment of sampling (aware UTC).
    """

    temperature_c: float
    humidity_pct: float
    measured_at: datetime
    raw_temperature: int
    raw_humidity: int

    def __post_init__(self) -> None:
        if self.measured_at.tzinfo is None:
            raise ValueError("measured_at must be timezone-aware (UTC)")


__all__ = [
    "HUMIDITY_MAX_PCT",
    "HUMIDITY_MIN_PCT",
    "TEMPERATURE_MAX_C",
    "TEMPERATURE_MIN_C",
    "Reading",
]
