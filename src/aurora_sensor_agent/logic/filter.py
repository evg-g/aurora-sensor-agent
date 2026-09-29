"""Signal conditioning: calibration offset, a median-of-N filter, and a bad-sample guard.

Why a median and not an average: a fridge sensor occasionally spits out a single wild value (a
bit-flip that passed CRC by chance, a momentary electrical glitch). A mean is dragged by that
outlier; a *median* ignores it as long as most of the window is good. That is exactly what you want
before feeding the excursion machine — one spurious 30 °C sample must not raise an alarm.

The guard rejects NaN and infinity outright. A NaN would silently poison every downstream
comparison (``nan > max`` is ``False``, so a NaN reading would look in-range forever), so a NaN in
the pipeline is one of the faults the catalogue injects, and this is where it is caught.
"""

from __future__ import annotations

import math
import statistics
from collections import deque

from aurora_sensor_agent.models import (
    HUMIDITY_MAX_PCT,
    HUMIDITY_MIN_PCT,
    TEMPERATURE_MAX_C,
    TEMPERATURE_MIN_C,
    Reading,
)


def is_valid_reading(reading: Reading) -> bool:
    """True if the reading's floats are finite and inside the sensor's physical range.

    Rejects NaN/inf (a poisoned sample) and values outside the SHT4x datasheet range, which can only
    come from a corrupt conversion that slipped through.
    """
    t, h = reading.temperature_c, reading.humidity_pct
    if not (math.isfinite(t) and math.isfinite(h)):
        return False
    if not (TEMPERATURE_MIN_C <= t <= TEMPERATURE_MAX_C):
        return False
    return HUMIDITY_MIN_PCT <= h <= HUMIDITY_MAX_PCT


def calibrate(reading: Reading, offset_c: float) -> Reading:
    """Return a copy of ``reading`` with the calibration offset added to the temperature.

    Each physical sensor has a small fixed error; the offset is measured once against a reference
    and then added to every sample. Humidity and the raw words are left untouched.
    """
    return Reading(
        temperature_c=reading.temperature_c + offset_c,
        humidity_pct=reading.humidity_pct,
        measured_at=reading.measured_at,
        raw_temperature=reading.raw_temperature,
        raw_humidity=reading.raw_humidity,
    )


class MedianFilter:
    """A rolling median-of-N over a fixed window.

    ``window`` samples are kept; ``push`` returns the median of everything seen so far, up to the
    window size. A window of 1 is a pass-through. Only finite values may be pushed — the caller runs
    :func:`is_valid_reading` first, so a NaN never reaches the window.
    """

    def __init__(self, window: int) -> None:
        if window < 1:
            raise ValueError(f"median window must be >= 1, got {window}")
        self._window = window
        self._values: deque[float] = deque(maxlen=window)

    @property
    def window(self) -> int:
        return self._window

    def push(self, value: float) -> float:
        """Add ``value`` and return the current median."""
        if not math.isfinite(value):
            raise ValueError(f"MedianFilter cannot accept a non-finite value: {value}")
        self._values.append(value)
        return statistics.median(self._values)

    def reset(self) -> None:
        """Forget the window (e.g. after a sensor reset)."""
        self._values.clear()


__all__ = ["MedianFilter", "calibrate", "is_valid_reading"]
