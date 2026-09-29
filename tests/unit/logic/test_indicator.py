"""Tests for the indicator's state→LED/buzzer mapping (pure, over fake pins)."""

from __future__ import annotations

import pytest

from aurora_sensor_agent.logic.excursion import ExcursionState
from aurora_sensor_agent.logic.indicator import IndicatorState, StatusIndicator, state_for
from tests.fakes.gpio import FakeGpioPin


@pytest.mark.parametrize(
    ("excursion_state", "expected"),
    [
        (ExcursionState.NORMAL, IndicatorState.OK),
        (ExcursionState.PENDING, IndicatorState.WARNING),
        (ExcursionState.CLEARING, IndicatorState.WARNING),
        (ExcursionState.EXCURSION, IndicatorState.ALARM),
    ],
)
def test_state_mapping(excursion_state: ExcursionState, expected: IndicatorState) -> None:
    assert state_for(excursion_state) is expected


def _indicator() -> tuple[StatusIndicator, dict[str, FakeGpioPin]]:
    pins = {name: FakeGpioPin() for name in ("green", "amber", "red", "buzzer")}
    indicator = StatusIndicator(pins["green"], pins["amber"], pins["red"], pins["buzzer"])
    return indicator, pins


def test_ok_lights_green_only() -> None:
    indicator, pins = _indicator()
    indicator.show(IndicatorState.OK)
    assert pins["green"].is_active
    assert not pins["amber"].is_active
    assert not pins["red"].is_active
    assert not pins["buzzer"].is_active


def test_warning_lights_amber_only() -> None:
    indicator, pins = _indicator()
    indicator.show(IndicatorState.WARNING)
    assert pins["amber"].is_active
    assert not pins["green"].is_active
    assert not pins["buzzer"].is_active


def test_alarm_lights_red_and_buzzer() -> None:
    indicator, pins = _indicator()
    indicator.show(IndicatorState.ALARM)
    assert pins["red"].is_active
    assert pins["buzzer"].is_active
    assert not pins["green"].is_active


def test_apply_translates_excursion_state() -> None:
    indicator, pins = _indicator()
    indicator.apply(ExcursionState.EXCURSION)
    assert indicator.state is IndicatorState.ALARM
    assert pins["red"].is_active


def test_all_off_clears_every_pin() -> None:
    indicator, pins = _indicator()
    indicator.show(IndicatorState.ALARM)
    indicator.all_off()
    assert not any(pin.is_active for pin in pins.values())
    assert indicator.state is None
