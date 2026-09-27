"""GPIO tier: drive the real ``gpiozero`` wrapper through ``MockFactory`` — no hardware.

``gpiozero`` ships a ``MockFactory`` that emulates pins in memory. Pointing ``Device.pin_factory``
at it lets ``real/gpio.py`` (which really calls ``gpiozero.OutputDevice``) run on a laptop, so the
same code path used on a Pi is exercised in CI. This is the GPIO double the spec asks for.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from aurora_sensor_agent.logic.indicator import IndicatorState, StatusIndicator
from aurora_sensor_agent.protocols import GpioPin
from aurora_sensor_agent.real.gpio import make_output_pin


@pytest.fixture(autouse=True)
def _mock_pins() -> Iterator[None]:
    from gpiozero import Device
    from gpiozero.pins.mock import MockFactory

    previous = Device.pin_factory
    Device.pin_factory = MockFactory()
    try:
        yield
    finally:
        Device.pin_factory = previous


def _active(pin: GpioPin) -> bool:
    """Read ``is_active`` through a function so mypy does not narrow it across ``high``/``low``."""
    return pin.is_active


def test_make_output_pin_drives_high_and_low() -> None:
    pin = make_output_pin(17)
    assert _active(pin) is False
    pin.high()
    assert _active(pin) is True
    pin.low()
    assert _active(pin) is False


def test_indicator_over_real_gpio_alarm() -> None:
    green = make_output_pin(17)
    amber = make_output_pin(27)
    red = make_output_pin(22)
    buzzer = make_output_pin(23)
    indicator = StatusIndicator(green, amber, red, buzzer)

    indicator.show(IndicatorState.ALARM)
    assert _active(red) and _active(buzzer)
    assert not _active(green) and not _active(amber)

    indicator.show(IndicatorState.OK)
    assert _active(green)
    assert not _active(red) and not _active(buzzer)


def test_pin_state_reaches_the_underlying_mock() -> None:
    # Prove we are really driving gpiozero, not just our wrapper's boolean.
    from gpiozero import Device

    pin = make_output_pin(24)
    pin.high()
    factory: Any = Device.pin_factory
    mock_pin = factory.pin(24)
    assert mock_pin.state == 1
