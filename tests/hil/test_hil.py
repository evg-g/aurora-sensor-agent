"""Hardware-in-the-loop: the driver against a real SHT4x over a real I²C bus.

Deselected by default (``@pytest.mark.hil``) and skipped without hardware (see conftest). On a wired
Raspberry Pi these read the actual chip, which is the only thing the fakes/sim/replay cannot prove:
that the real bus wiring, timing, and CRC handling work against silicon.
"""

from __future__ import annotations

import pytest

from aurora_sensor_agent.clock import SystemClock
from aurora_sensor_agent.drivers.sht4x import Precision, Sht4xDriver
from aurora_sensor_agent.real.i2c import RealI2CBus

pytestmark = pytest.mark.hil


def _driver() -> Sht4xDriver:
    return Sht4xDriver(RealI2CBus(), SystemClock())


def test_real_sht4x_reads_plausible_room_conditions() -> None:
    reading = _driver().measure(Precision.HIGH)
    assert -10.0 < reading.temperature_c < 60.0
    assert 0.0 <= reading.humidity_pct <= 100.0


def test_real_sht4x_two_reads_are_close() -> None:
    driver = _driver()
    first = driver.measure(Precision.HIGH)
    second = driver.measure(Precision.HIGH)
    # Ambient temperature does not jump between back-to-back reads.
    assert abs(first.temperature_c - second.temperature_c) < 2.0
