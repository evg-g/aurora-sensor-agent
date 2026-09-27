"""Register-level driver for the Sensirion SHT4x temperature + humidity sensor.

This is the code that would run on the Raspberry Pi, but it never imports a hardware library. It
talks to an ``I2CBus`` seam, so the *same* driver drives real hardware, the simulator, or a
recorded trace. That is the whole point of milestone 8.

The SHT4x conversation (from the datasheet):

1. Write a one-byte command (e.g. ``0xFD`` = measure, high precision).
2. Wait the measurement time — the chip is busy converting and will NACK or return stale bytes if
   read too early. High precision needs up to ~8.3 ms; we wait a hair longer.
3. Read 6 bytes: ``[T_msb, T_lsb, T_crc, RH_msb, RH_lsb, RH_crc]`` — two 16-bit words, each
   followed by its own CRC-8 (see ``protocol/crc.py``).
4. Verify both checksums, then convert the raw 16-bit values to °C and %RH.

Conversion formulas (datasheet, 16-bit full scale = 65535):

    T[°C]  = -45 + 175 * raw_t  / 65535
    RH[%]  =  -6 + 125 * raw_rh / 65535   (then clamped to 0..100)

The clamp matters: the linear formula can produce -6 %RH or 119 %RH near the rails, which are not
physically meaningful, so humidity is pinned to [0, 100].
"""

from __future__ import annotations

from enum import Enum

from aurora_sensor_agent.models import (
    HUMIDITY_MAX_PCT,
    HUMIDITY_MIN_PCT,
    Reading,
)
from aurora_sensor_agent.protocol.crc import verify_word
from aurora_sensor_agent.protocols import Clock, I2CBus

DEFAULT_ADDRESS = 0x44
"""The SHT4x's default 7-bit I²C address (ADDR pin low)."""

_FULL_SCALE = 65535
_MEASUREMENT_FRAME_LEN = 6  # two words, each two bytes + one CRC byte
_SERIAL_FRAME_LEN = 6

# Command byte -> soft-reset / serial commands. Kept as named constants, not magic numbers.
_CMD_SOFT_RESET = 0x94
_CMD_READ_SERIAL = 0x89
_SOFT_RESET_DELAY_S = 0.001
_SERIAL_READ_DELAY_S = 0.001


class Precision(Enum):
    """Measurement precision: higher precision costs a longer conversion time.

    Each member carries its command byte and the conversion time to wait before reading, taken
    from the datasheet's maximum figures (with a small margin).
    """

    HIGH = (0xFD, 0.0090)
    MEDIUM = (0xF6, 0.0050)
    LOW = (0xE0, 0.0020)

    def __init__(self, command: int, delay_s: float) -> None:
        self.command = command
        self.delay_s = delay_s


def raw_to_celsius(raw: int) -> float:
    """Convert a 16-bit raw temperature word to degrees Celsius."""
    if not 0 <= raw <= _FULL_SCALE:
        raise ValueError(f"raw temperature out of range 0..{_FULL_SCALE}: {raw}")
    return -45.0 + 175.0 * raw / _FULL_SCALE


def raw_to_humidity(raw: int) -> float:
    """Convert a 16-bit raw humidity word to %RH, clamped to the physical 0..100 range."""
    if not 0 <= raw <= _FULL_SCALE:
        raise ValueError(f"raw humidity out of range 0..{_FULL_SCALE}: {raw}")
    rh = -6.0 + 125.0 * raw / _FULL_SCALE
    return min(HUMIDITY_MAX_PCT, max(HUMIDITY_MIN_PCT, rh))


class Sht4xDriver:
    """Drives an SHT4x over any ``I2CBus``, using an injected ``Clock`` for the measurement wait."""

    def __init__(self, bus: I2CBus, clock: Clock, address: int = DEFAULT_ADDRESS) -> None:
        if not 0x08 <= address <= 0x77:
            raise ValueError(f"I²C address out of the 7-bit range 0x08..0x77: 0x{address:02X}")
        self._bus = bus
        self._clock = clock
        self._address = address

    def measure(self, precision: Precision = Precision.HIGH) -> Reading:
        """Take one reading: command, wait, read 6 bytes, verify CRCs, convert.

        Raises ``CrcError`` if either checksum is wrong, ``OSError`` on a bus error, and
        ``ValueError`` if the chip returns the wrong number of bytes.
        """
        self._bus.write(self._address, bytes((precision.command,)))
        self._clock.sleep(precision.delay_s)
        frame = self._bus.read(self._address, _MEASUREMENT_FRAME_LEN)
        measured_at = self._clock.now()

        raw_t, raw_rh = self._parse_two_words(frame, _MEASUREMENT_FRAME_LEN)
        return Reading(
            temperature_c=raw_to_celsius(raw_t),
            humidity_pct=raw_to_humidity(raw_rh),
            measured_at=measured_at,
            raw_temperature=raw_t,
            raw_humidity=raw_rh,
        )

    def soft_reset(self) -> None:
        """Send the soft-reset command and wait for the chip to come back up."""
        self._bus.write(self._address, bytes((_CMD_SOFT_RESET,)))
        self._clock.sleep(_SOFT_RESET_DELAY_S)

    def read_serial_number(self) -> int:
        """Read the chip's unique 32-bit serial number (two CRC-checked words)."""
        self._bus.write(self._address, bytes((_CMD_READ_SERIAL,)))
        self._clock.sleep(_SERIAL_READ_DELAY_S)
        frame = self._bus.read(self._address, _SERIAL_FRAME_LEN)
        high, low = self._parse_two_words(frame, _SERIAL_FRAME_LEN)
        return (high << 16) | low

    @staticmethod
    def _parse_two_words(frame: bytes, expected_len: int) -> tuple[int, int]:
        """Split a 6-byte frame into two CRC-verified 16-bit words."""
        if len(frame) != expected_len:
            raise ValueError(f"expected {expected_len} bytes from the sensor, got {len(frame)}")
        first = verify_word(frame[0], frame[1], frame[2])
        second = verify_word(frame[3], frame[4], frame[5])
        return first, second


__all__ = [
    "DEFAULT_ADDRESS",
    "Precision",
    "Sht4xDriver",
    "raw_to_celsius",
    "raw_to_humidity",
]
