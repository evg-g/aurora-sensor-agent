"""Map the excursion state to the status LED colour and the buzzer, over ``GpioPin`` seams.

The device has a three-colour status LED (green / amber / red) and a buzzer. This module owns the
policy of which is on when, and drives four ``GpioPin`` outputs. It has no hardware knowledge — the
pins are seams, so the same code drives real GPIO on a Pi (``real/gpio.py``) or ``gpiozero``'s mock
pins in a test.

Colour policy:

    NORMAL              → green   (all is well)
    PENDING / CLEARING  → amber   (something is off, but not yet / no longer a confirmed excursion)
    EXCURSION           → red + buzzer (a real cold-chain breach: alarm)
"""

from __future__ import annotations

from enum import Enum

from aurora_sensor_agent.logic.excursion import ExcursionState
from aurora_sensor_agent.protocols import GpioPin


class IndicatorState(Enum):
    """What the panel should show."""

    OK = "ok"
    WARNING = "warning"
    ALARM = "alarm"


def state_for(excursion_state: ExcursionState) -> IndicatorState:
    """Translate an excursion-machine state into an indicator state."""
    if excursion_state is ExcursionState.NORMAL:
        return IndicatorState.OK
    if excursion_state is ExcursionState.EXCURSION:
        return IndicatorState.ALARM
    # PENDING and CLEARING are both "watch this".
    return IndicatorState.WARNING


class StatusIndicator:
    """Drives the green/amber/red LED and the buzzer from an indicator state."""

    def __init__(self, green: GpioPin, amber: GpioPin, red: GpioPin, buzzer: GpioPin) -> None:
        self._green = green
        self._amber = amber
        self._red = red
        self._buzzer = buzzer
        self._state: IndicatorState | None = None

    @property
    def state(self) -> IndicatorState | None:
        return self._state

    def show(self, state: IndicatorState) -> None:
        """Set the pins for ``state`` — exactly one LED on, buzzer only on alarm."""
        self._set(self._green, state is IndicatorState.OK)
        self._set(self._amber, state is IndicatorState.WARNING)
        self._set(self._red, state is IndicatorState.ALARM)
        self._set(self._buzzer, state is IndicatorState.ALARM)
        self._state = state

    def apply(self, excursion_state: ExcursionState) -> None:
        """Convenience: translate an excursion state and show it."""
        self.show(state_for(excursion_state))

    def all_off(self) -> None:
        for pin in (self._green, self._amber, self._red, self._buzzer):
            pin.low()
        self._state = None

    @staticmethod
    def _set(pin: GpioPin, on: bool) -> None:
        if on:
            pin.high()
        else:
            pin.low()


__all__ = ["IndicatorState", "StatusIndicator", "state_for"]
