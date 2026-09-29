"""A fake ``GpioPin`` for pure indicator tests.

A working in-memory pin: ``high``/``low`` flip a boolean, ``is_active`` reads it back. It lets the
indicator's colour logic be tested with no ``gpiozero`` at all; the ``gpiozero`` ``MockFactory``
path is exercised separately in ``tests/unit/gpio/``.
"""

from __future__ import annotations


class FakeGpioPin:
    """A ``GpioPin`` that just remembers whether it is driven high."""

    def __init__(self) -> None:
        self._active = False

    def high(self) -> None:
        self._active = True

    def low(self) -> None:
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active


__all__ = ["FakeGpioPin"]
