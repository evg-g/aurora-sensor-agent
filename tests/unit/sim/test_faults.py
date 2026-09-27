"""Fault-injection tests for the simulated SHT4x bus, driven through the real driver.

Each test injects one fault at a measurement index and proves the driver reacts the right way, then
(for transient faults) that the very next reading succeeds — the behaviour a retry/backoff layer
will rely on in milestone 9.
"""

from __future__ import annotations

import pytest

from aurora_sensor_agent.drivers.sht4x import Sht4xDriver
from aurora_sensor_agent.models import TEMPERATURE_MAX_C, TEMPERATURE_MIN_C
from aurora_sensor_agent.protocol.crc import CrcError
from aurora_sensor_agent.sim.faults import Sht4xFault
from aurora_sensor_agent.sim.i2c import DEFAULT_ADDRESS, DEFAULT_SERIAL_NUMBER, SimulatedSht4xBus
from aurora_sensor_agent.sim.thermal import ThermalModel
from tests.fakes.clock import FakeClock


def _driver(faults: dict[int, Sht4xFault] | None = None) -> Sht4xDriver:
    clock = FakeClock()
    bus = SimulatedSht4xBus(clock, ThermalModel(seed=7), faults=faults)
    return Sht4xDriver(bus, clock)


def test_clean_read_returns_a_plausible_reading() -> None:
    reading = _driver().measure()

    assert TEMPERATURE_MIN_C <= reading.temperature_c <= TEMPERATURE_MAX_C
    assert 0.0 <= reading.humidity_pct <= 100.0


def test_bad_crc_is_rejected_then_recovers() -> None:
    driver = _driver({0: Sht4xFault.BAD_CRC})

    with pytest.raises(CrcError):
        driver.measure()
    # Transient: the next reading is clean.
    assert driver.measure() is not None


def test_nack_raises_oserror_then_recovers() -> None:
    driver = _driver({0: Sht4xFault.NACK})

    with pytest.raises(OSError, match="NACK"):
        driver.measure()
    assert driver.measure() is not None


def test_timeout_raises_timeouterror_then_recovers() -> None:
    driver = _driver({0: Sht4xFault.TIMEOUT})

    with pytest.raises(TimeoutError):
        driver.measure()
    assert driver.measure() is not None


def test_short_read_is_rejected() -> None:
    driver = _driver({0: Sht4xFault.SHORT_READ})

    with pytest.raises(ValueError, match="expected 6 bytes"):
        driver.measure()


def test_power_loss_kills_the_bus() -> None:
    driver = _driver({0: Sht4xFault.POWER_LOSS})

    with pytest.raises(OSError, match="power lost"):
        driver.measure()
    # The bus stays dead until it is reopened (a new bus object).
    with pytest.raises(OSError, match="closed"):
        driver.measure()


def test_stuck_sensor_freezes_on_its_last_value() -> None:
    driver = _driver({0: Sht4xFault.STUCK})

    first = driver.measure()
    second = driver.measure()

    assert first.raw_temperature == second.raw_temperature
    assert first.raw_humidity == second.raw_humidity


def test_reading_before_conversion_time_fails() -> None:
    clock = FakeClock()
    bus = SimulatedSht4xBus(clock, ThermalModel(seed=1))

    bus.write(DEFAULT_ADDRESS, b"\xfd")
    # No sleep: the chip is still converting, so the read must fail like a real NACK.
    with pytest.raises(OSError, match="too early"):
        bus.read(DEFAULT_ADDRESS, 6)


def test_unknown_command_is_rejected() -> None:
    bus = SimulatedSht4xBus(FakeClock(), ThermalModel(seed=1))

    with pytest.raises(OSError, match="unknown SHT4x command"):
        bus.write(DEFAULT_ADDRESS, b"\x00")


def test_wrong_address_has_no_device() -> None:
    bus = SimulatedSht4xBus(FakeClock(), ThermalModel(seed=1))

    with pytest.raises(OSError, match="no device"):
        bus.write(0x45, b"\xfd")


def test_serial_number_round_trips_through_the_driver() -> None:
    assert _driver().read_serial_number() == DEFAULT_SERIAL_NUMBER
