"""The real ``SerialPort`` — a thin factory over ``pyserial``.

Like ``real/i2c.py``, the ``pyserial`` import is lazy (inside the factory) so this module loads on
any laptop with no serial hardware. ``serial_for_url`` handles both a real device path
(``/dev/ttyAMA0``) and the test URLs ``loop://`` (an in-memory loopback) and ``socket://``, which is
what lets the serial tier run with no hardware. A ``pyserial`` ``Serial`` already has ``read``,
``write`` and ``close`` with the right shapes, so it satisfies the ``SerialPort`` protocol directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aurora_sensor_agent.protocols import SerialPort


def open_serial_port(url: str, *, baudrate: int = 9600, timeout: float = 1.0) -> SerialPort:
    """Open a serial port by device path or ``pyserial`` URL. Raises if ``pyserial`` is missing."""
    import serial  # lazy: only needed when actually opening a port

    port = serial.serial_for_url(url, baudrate=baudrate, timeout=timeout)
    return port  # type: ignore[no-any-return]


__all__ = ["open_serial_port"]
