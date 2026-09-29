"""The shared driver-contract suite, run against sim, replay, and (skipped) real hardware.

``Sht4xStackContract`` holds the tests; each ``Test*`` subclass supplies a bus. The base class has
no ``Test`` prefix, so pytest collects only the concrete subclasses.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aurora_sensor_agent.drivers.sht4x import Sht4xDriver
from aurora_sensor_agent.models import (
    HUMIDITY_MAX_PCT,
    HUMIDITY_MIN_PCT,
    TEMPERATURE_MAX_C,
    TEMPERATURE_MIN_C,
    Reading,
)
from aurora_sensor_agent.protocols import Clock, I2CBus
from aurora_sensor_agent.real.i2c import RealI2CBus
from aurora_sensor_agent.replay.i2c import ReplayI2CBus
from aurora_sensor_agent.sim.i2c import SimulatedSht4xBus
from aurora_sensor_agent.sim.thermal import ThermalModel
from tests.fakes.clock import FakeClock

_TRACE = Path(__file__).parent.parent / "fixtures" / "traces" / "sim_baseline.jsonl"


class Sht4xStackContract:
    """Behaviour every sensor stack must satisfy. Subclasses supply the bus."""

    def make_bus(self, clock: Clock) -> I2CBus:
        raise NotImplementedError

    def _driver(self) -> Sht4xDriver:
        clock = FakeClock()
        return Sht4xDriver(self.make_bus(clock), clock)

    def test_measure_returns_a_reading(self) -> None:
        assert isinstance(self._driver().measure(), Reading)

    def test_temperature_is_in_the_physical_range(self) -> None:
        reading = self._driver().measure()
        assert TEMPERATURE_MIN_C <= reading.temperature_c <= TEMPERATURE_MAX_C

    def test_humidity_is_in_range(self) -> None:
        reading = self._driver().measure()
        assert HUMIDITY_MIN_PCT <= reading.humidity_pct <= HUMIDITY_MAX_PCT

    def test_reading_is_timestamped_aware_utc(self) -> None:
        reading = self._driver().measure()
        assert reading.measured_at.tzinfo is not None

    def test_several_readings_all_valid(self) -> None:
        driver = self._driver()
        for _ in range(10):
            reading = driver.measure()
            assert TEMPERATURE_MIN_C <= reading.temperature_c <= TEMPERATURE_MAX_C
            assert HUMIDITY_MIN_PCT <= reading.humidity_pct <= HUMIDITY_MAX_PCT


class TestSimStack(Sht4xStackContract):
    def make_bus(self, clock: Clock) -> I2CBus:
        return SimulatedSht4xBus(clock, ThermalModel(seed=7))


class TestReplayStack(Sht4xStackContract):
    def make_bus(self, clock: Clock) -> I2CBus:
        return ReplayI2CBus.from_jsonl(_TRACE)


class TestRealStack(Sht4xStackContract):
    def make_bus(self, clock: Clock) -> I2CBus:
        pytest.skip("real I²C bus needs a Raspberry Pi with an SHT4x wired to /dev/i2c-1")


def test_real_bus_imports_and_constructs_without_hardware() -> None:
    # Proves the lazy-import rule: no smbus2, no /dev/i2c-* required to build the object.
    assert RealI2CBus() is not None


def test_real_bus_defers_hardware_import_until_first_use() -> None:
    # smbus2 is not a dependency, so the first real bus operation is where it would fail.
    bus = RealI2CBus()
    with pytest.raises(ModuleNotFoundError):
        bus.write(0x44, b"\xfd")
