"""A register-level SHT4x chip simulator behind the ``I2CBus`` seam.

This pretends to be the actual chip on the wire: it accepts the same command bytes, enforces the
same conversion delay (a read that comes too early fails, exactly as the real chip NACKs while it
is still converting), and returns properly framed 6-byte responses — two 16-bit words, each with a
real CRC-8. The unmodified ``Sht4xDriver`` runs against it without knowing it is not real silicon.

Temperature and humidity come from a seeded ``ThermalModel`` sampled at the instant the command was
issued, so the whole thing is deterministic in time. Faults from ``sim.faults`` can be injected at a
chosen measurement index to corrupt the exchange on purpose.
"""

from __future__ import annotations

from collections.abc import Mapping

from aurora_sensor_agent.protocol.crc import crc8
from aurora_sensor_agent.protocols import Clock
from aurora_sensor_agent.sim.faults import READ_FAULTS, WRITE_FAULTS, Sht4xFault
from aurora_sensor_agent.sim.thermal import ThermalModel

DEFAULT_ADDRESS = 0x44
DEFAULT_SERIAL_NUMBER = 0x0D15EA5E
_FULL_SCALE = 65535
_MEASUREMENT_FRAME_LEN = 6

# Command byte -> conversion time the chip needs before data is ready (datasheet maxima).
_MEASURE_COMMANDS: dict[int, float] = {
    0xFD: 0.0083,  # high precision
    0xF6: 0.0045,  # medium precision
    0xE0: 0.0016,  # low precision
}
_CMD_SOFT_RESET = 0x94
_CMD_READ_SERIAL = 0x89
_SOFT_RESET_TIME_S = 0.0010
_SERIAL_TIME_S = 0.0005
_READY_EPSILON_S = 1e-9  # float slack so an exactly-long-enough wait counts as ready


def celsius_to_raw(temperature_c: float) -> int:
    """Inverse of the driver's conversion: °C -> 16-bit raw word (the chip's job)."""
    raw = round((temperature_c + 45.0) / 175.0 * _FULL_SCALE)
    return max(0, min(_FULL_SCALE, raw))


def humidity_to_raw(humidity_pct: float) -> int:
    """Inverse of the driver's conversion: %RH -> 16-bit raw word."""
    raw = round((humidity_pct + 6.0) / 125.0 * _FULL_SCALE)
    return max(0, min(_FULL_SCALE, raw))


def encode_word(raw: int) -> bytes:
    """Encode a 16-bit value the way the chip does: MSB, LSB, CRC-8 over those two bytes."""
    msb = (raw >> 8) & 0xFF
    lsb = raw & 0xFF
    return bytes((msb, lsb, crc8(bytes((msb, lsb)))))


class SimulatedSht4xBus:
    """An ``I2CBus`` that behaves like an SHT4x on an I²C wire."""

    def __init__(
        self,
        clock: Clock,
        thermal: ThermalModel | None = None,
        *,
        address: int = DEFAULT_ADDRESS,
        serial_number: int = DEFAULT_SERIAL_NUMBER,
        faults: Mapping[int, Sht4xFault] | None = None,
    ) -> None:
        self._clock = clock
        self._thermal = thermal if thermal is not None else ThermalModel()
        self._address = address
        self._serial = serial_number & 0xFFFFFFFF
        self._faults: dict[int, Sht4xFault] = dict(faults or {})
        self._pending_cmd: int | None = None
        self._cmd_time: float = 0.0
        self._measure_count = 0
        self._stuck_frame: bytes | None = None
        self._closed = False

    # -- I2CBus protocol -------------------------------------------------------------------

    def write(self, address: int, data: bytes) -> None:
        self._require_open()
        self._require_address(address)
        if len(data) != 1:
            raise OSError(f"SHT4x commands are a single byte, got {len(data)}")
        command = data[0]
        if command not in _MEASURE_COMMANDS and command not in (_CMD_SOFT_RESET, _CMD_READ_SERIAL):
            raise OSError(f"unknown SHT4x command 0x{command:02X}")

        if command in _MEASURE_COMMANDS:
            fault = self._faults.get(self._measure_count)
            if fault in WRITE_FAULTS:
                del self._faults[self._measure_count]
                if fault is Sht4xFault.POWER_LOSS:
                    self._closed = True
                    raise OSError("power lost mid-write")
                raise OSError("device did not acknowledge the command (NACK)")

        self._pending_cmd = command
        self._cmd_time = self._clock.monotonic()

    def read(self, address: int, length: int) -> bytes:
        self._require_open()
        self._require_address(address)
        if self._pending_cmd is None:
            raise OSError("read issued without a preceding command")

        command = self._pending_cmd
        self._pending_cmd = None
        self._require_ready(command)

        if command == _CMD_READ_SERIAL:
            return self._serial_frame()[:length]

        # A measurement command.
        fault = self._faults.get(self._measure_count)
        if fault in READ_FAULTS:
            del self._faults[self._measure_count]
            return self._apply_read_fault(fault, length)

        frame = self._stuck_frame if self._stuck_frame is not None else self._measurement_frame()
        self._measure_count += 1
        return frame[:length]

    def close(self) -> None:
        self._closed = True

    # -- internals -------------------------------------------------------------------------

    def _apply_read_fault(self, fault: Sht4xFault, length: int) -> bytes:
        if fault is Sht4xFault.TIMEOUT:
            raise TimeoutError("I²C read timed out")
        frame = self._measurement_frame()
        if fault is Sht4xFault.BAD_CRC:
            corrupted = bytearray(frame)
            corrupted[2] ^= 0xFF  # wreck the temperature word's CRC byte
            self._measure_count += 1
            return bytes(corrupted)[:length]
        if fault is Sht4xFault.SHORT_READ:
            self._measure_count += 1
            return frame[: max(0, length - 1)]
        # STUCK: freeze on the current value from now on.
        self._stuck_frame = frame
        self._measure_count += 1
        return frame[:length]

    def _measurement_frame(self) -> bytes:
        temperature_c, humidity_pct = self._thermal.sample(self._cmd_time)
        return encode_word(celsius_to_raw(temperature_c)) + encode_word(
            humidity_to_raw(humidity_pct)
        )

    def _serial_frame(self) -> bytes:
        high = (self._serial >> 16) & 0xFFFF
        low = self._serial & 0xFFFF
        return encode_word(high) + encode_word(low)

    def _require_open(self) -> None:
        if self._closed:
            raise OSError("I²C bus is closed")

    def _require_address(self, address: int) -> None:
        if address != self._address:
            raise OSError(f"no device at address 0x{address:02X}")

    def _require_ready(self, command: int) -> None:
        required = _MEASURE_COMMANDS.get(command)
        if required is None:
            required = _SERIAL_TIME_S if command == _CMD_READ_SERIAL else _SOFT_RESET_TIME_S
        elapsed = self._clock.monotonic() - self._cmd_time
        if elapsed < required - _READY_EPSILON_S:
            raise OSError(
                f"read too early: waited {elapsed * 1000:.2f} ms, "
                f"chip needs {required * 1000:.2f} ms"
            )


__all__ = [
    "DEFAULT_ADDRESS",
    "DEFAULT_SERIAL_NUMBER",
    "SimulatedSht4xBus",
    "celsius_to_raw",
    "encode_word",
    "humidity_to_raw",
]
