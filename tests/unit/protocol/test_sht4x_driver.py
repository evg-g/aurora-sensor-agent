"""Register-level tests for the SHT4x driver: command bytes, timing, framing, CRC, conversion.

No hardware and no simulator physics — the bus is a scripted fake that hands back exactly the bytes
we choose, so each test isolates one part of the wire protocol.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from aurora_sensor_agent.drivers.sht4x import (
    DEFAULT_ADDRESS,
    Precision,
    Sht4xDriver,
    raw_to_celsius,
    raw_to_humidity,
)
from aurora_sensor_agent.protocol.crc import CrcError, crc8
from aurora_sensor_agent.sim.i2c import celsius_to_raw, encode_word
from tests.fakes.clock import FakeClock
from tests.fakes.i2c import ScriptedI2CBus


def _frame(raw_t: int, raw_rh: int) -> bytes:
    return encode_word(raw_t) + encode_word(raw_rh)


def test_measure_sends_high_precision_command_and_waits() -> None:
    # Arrange
    bus = ScriptedI2CBus([_frame(25000, 30000)])
    clock = FakeClock()
    driver = Sht4xDriver(bus, clock)

    # Act
    driver.measure(Precision.HIGH)

    # Assert: exactly the 0xFD command to the default address, and the conversion wait elapsed.
    assert bus.writes == [(DEFAULT_ADDRESS, b"\xfd")]
    assert clock.monotonic() == pytest.approx(Precision.HIGH.delay_s)


def test_measure_uses_low_precision_command_and_shorter_wait() -> None:
    bus = ScriptedI2CBus([_frame(10000, 20000)])
    clock = FakeClock()
    driver = Sht4xDriver(bus, clock)

    driver.measure(Precision.LOW)

    assert bus.writes == [(DEFAULT_ADDRESS, bytes((Precision.LOW.command,)))]
    assert clock.monotonic() == pytest.approx(Precision.LOW.delay_s)


def test_measure_converts_rail_values_exactly() -> None:
    # raw 0 -> -45 °C and -6 %RH (clamped to 0); raw 65535 -> 130 °C and 100 %RH.
    bus = ScriptedI2CBus([_frame(0, 0), _frame(65535, 65535)])
    driver = Sht4xDriver(bus, FakeClock())

    low = driver.measure()
    high = driver.measure()

    assert low.temperature_c == pytest.approx(-45.0)
    assert low.humidity_pct == pytest.approx(0.0)  # -6 %RH clamped up to 0
    assert high.temperature_c == pytest.approx(130.0)
    assert high.humidity_pct == pytest.approx(100.0)  # 119 %RH clamped down to 100


def test_measure_keeps_raw_words_for_replay() -> None:
    bus = ScriptedI2CBus([_frame(25000, 30000)])
    driver = Sht4xDriver(bus, FakeClock())

    reading = driver.measure()

    assert reading.raw_temperature == 25000
    assert reading.raw_humidity == 30000


def test_measure_timestamps_reading_from_the_clock() -> None:
    bus = ScriptedI2CBus([_frame(25000, 30000)])
    clock = FakeClock()
    driver = Sht4xDriver(bus, clock)

    reading = driver.measure()

    # measured_at is taken after the conversion wait, so it is the epoch + the delay.
    assert reading.measured_at == clock.now()
    assert reading.measured_at.tzinfo is not None


def test_measure_rejects_corrupted_crc() -> None:
    frame = bytearray(_frame(25000, 30000))
    frame[2] ^= 0x01  # flip a bit in the temperature word's CRC
    driver = Sht4xDriver(ScriptedI2CBus([bytes(frame)]), FakeClock())

    with pytest.raises(CrcError):
        driver.measure()


def test_measure_rejects_short_frame() -> None:
    driver = Sht4xDriver(ScriptedI2CBus([_frame(1, 1)[:5]]), FakeClock())

    with pytest.raises(ValueError, match="expected 6 bytes"):
        driver.measure()


def test_soft_reset_sends_reset_command() -> None:
    bus = ScriptedI2CBus([])
    driver = Sht4xDriver(bus, FakeClock())

    driver.soft_reset()

    assert bus.writes == [(DEFAULT_ADDRESS, b"\x94")]


def test_read_serial_number_combines_two_words() -> None:
    serial = 0x0D15EA5E
    high, low = (serial >> 16) & 0xFFFF, serial & 0xFFFF
    bus = ScriptedI2CBus([encode_word(high) + encode_word(low)])
    driver = Sht4xDriver(bus, FakeClock())

    assert driver.read_serial_number() == serial
    assert bus.writes == [(DEFAULT_ADDRESS, b"\x89")]


@pytest.mark.parametrize("bad_address", [0x00, 0x07, 0x78, 0x80])
def test_constructor_rejects_out_of_range_address(bad_address: int) -> None:
    with pytest.raises(ValueError, match="7-bit"):
        Sht4xDriver(ScriptedI2CBus([]), FakeClock(), address=bad_address)


# -- conversion functions ------------------------------------------------------------------


def test_raw_to_celsius_known_points() -> None:
    assert raw_to_celsius(0) == pytest.approx(-45.0)
    assert raw_to_celsius(65535) == pytest.approx(130.0)


def test_raw_to_humidity_clamps_below_zero_and_above_hundred() -> None:
    assert raw_to_humidity(0) == pytest.approx(0.0)  # formula gives -6, clamped
    assert raw_to_humidity(65535) == pytest.approx(100.0)  # formula gives 119, clamped


@pytest.mark.parametrize("bad_raw", [-1, 65536, 100000])
def test_conversion_rejects_out_of_range_raw(bad_raw: int) -> None:
    with pytest.raises(ValueError):
        raw_to_celsius(bad_raw)
    with pytest.raises(ValueError):
        raw_to_humidity(bad_raw)


@given(raw=st.integers(0, 65535))
def test_temperature_encode_decode_round_trips(raw: int) -> None:
    # Property: the chip's encoder and the driver's decoder are inverses (within rounding).
    assert celsius_to_raw(raw_to_celsius(raw)) == pytest.approx(raw, abs=1)


@given(msb=st.integers(0, 0xFF), lsb=st.integers(0, 0xFF))
def test_encode_word_produces_a_crc_the_driver_accepts(msb: int, lsb: int) -> None:
    word = encode_word((msb << 8) | lsb)
    assert word[2] == crc8(bytes((msb, lsb)))
