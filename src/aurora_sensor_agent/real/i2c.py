"""Real I²C bus using ``smbus2`` on a Raspberry Pi.

The import of ``smbus2`` is deferred to the first actual bus operation. That is deliberate: it
lets this module be imported and type-checked on a developer laptop or in CI where ``smbus2`` is
not installed and ``/dev/i2c-*`` does not exist. Construction is also cheap and hardware-free; the
device is only opened on the first ``write``/``read``.

The SHT4x needs *raw* I²C transactions (a plain write of the command byte, then a plain read of
the data bytes), not SMBus register reads, so this uses ``i2c_rdwr`` with ``i2c_msg`` messages.
"""

from __future__ import annotations

from typing import Any

DEFAULT_BUS_NUMBER = 1  # /dev/i2c-1 on a Raspberry Pi


class RealI2CBus:
    """An ``I2CBus`` backed by a physical Linux I²C adapter via ``smbus2``."""

    def __init__(self, bus_number: int = DEFAULT_BUS_NUMBER) -> None:
        self._bus_number = bus_number
        self._smbus: Any = None  # opened lazily on first use

    def _ensure_open(self) -> Any:
        if self._smbus is None:
            from smbus2 import SMBus  # lazy: only needed with real hardware

            self._smbus = SMBus(self._bus_number)
        return self._smbus

    def write(self, address: int, data: bytes) -> None:
        from smbus2 import i2c_msg

        smbus = self._ensure_open()
        smbus.i2c_rdwr(i2c_msg.write(address, data))

    def read(self, address: int, length: int) -> bytes:
        from smbus2 import i2c_msg

        smbus = self._ensure_open()
        message = i2c_msg.read(address, length)
        smbus.i2c_rdwr(message)
        return bytes(message)

    def close(self) -> None:
        if self._smbus is not None:
            self._smbus.close()
            self._smbus = None


__all__ = ["DEFAULT_BUS_NUMBER", "RealI2CBus"]
