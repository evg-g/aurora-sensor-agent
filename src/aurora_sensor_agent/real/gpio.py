"""The real ``GpioPin`` — a thin wrapper over ``gpiozero``.

The ``gpiozero`` import is lazy so the package loads with no GPIO backend present. In tests the pins
are driven through ``gpiozero``'s own ``MockFactory`` (set once via ``Device.pin_factory``), which
needs no hardware — so ``real/gpio.py`` is exercised on a laptop, not just on a Pi.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aurora_sensor_agent.protocols import GpioPin


class GpiozeroPin:
    """A ``GpioPin`` backed by a ``gpiozero.OutputDevice``."""

    def __init__(self, device: Any) -> None:
        self._device = device

    def high(self) -> None:
        self._device.on()

    def low(self) -> None:
        self._device.off()

    @property
    def is_active(self) -> bool:
        return bool(self._device.value)

    def close(self) -> None:
        self._device.close()


def make_output_pin(pin: int | str, *, active_high: bool = True) -> GpioPin:
    """Create a GPIO output on ``pin``. Raises if ``gpiozero`` is missing."""
    from gpiozero import OutputDevice  # lazy

    return GpiozeroPin(OutputDevice(pin, active_high=active_high))


__all__ = ["GpiozeroPin", "make_output_pin"]
