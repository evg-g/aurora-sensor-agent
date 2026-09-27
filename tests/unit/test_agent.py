"""Tests for the agent run loop, wired from fakes: scripted sensor, in-memory buffer and transport.

No hardware, no network, no Docker — the SQLite buffer is ``:memory:`` and the transport is a Python
list. A ``FakeClock`` makes the sample interval and the backoff sleeps instant.
"""

from __future__ import annotations

import math

from aurora_sensor_agent.agent import SensorAgent
from aurora_sensor_agent.buffer.sqlite import SqliteBufferStore
from aurora_sensor_agent.config import AgentConfig, BackoffConfig, ThresholdPolicy
from aurora_sensor_agent.logic.excursion import ExcursionState
from aurora_sensor_agent.logic.indicator import IndicatorState, StatusIndicator
from aurora_sensor_agent.models import Reading
from aurora_sensor_agent.protocols import Clock
from aurora_sensor_agent.transport.memory import InMemoryTransport
from tests.fakes.clock import FakeClock
from tests.fakes.gpio import FakeGpioPin


class ScriptedSensor:
    """Returns readings (or raises) from a script, stamping each with the current fake clock."""

    def __init__(self, clock: Clock, script: list[float | Exception]) -> None:
        self._clock = clock
        self._script = script
        self._index = 0

    def __call__(self) -> Reading:
        item = self._script[self._index]
        self._index += 1
        if isinstance(item, Exception):
            raise item
        return Reading(
            temperature_c=item,
            humidity_pct=45.0,
            measured_at=self._clock.now(),
            raw_temperature=0,
            raw_humidity=0,
        )


def _config(**overrides: object) -> AgentConfig:
    base: dict[str, object] = {
        "device_id": "fridge-A",
        "clinic_id": "clinic-1",
        "sample_interval_seconds": 30.0,
        "median_window": 1,
        "buffer_capacity": 1000,
        "batch_max_readings": 50,
        "thresholds": ThresholdPolicy(
            min_temperature_c=2.0, max_temperature_c=8.0, dwell_minutes=0.1, recovery_minutes=0.1
        ),
        "backoff": BackoffConfig(base_seconds=1.0, factor=2.0, max_seconds=5.0, jitter=False),
        "max_clock_skew_seconds": 60.0,
    }
    base.update(overrides)
    return AgentConfig(**base)  # type: ignore[arg-type]


def _agent(
    clock: FakeClock,
    script: list[float | Exception],
    *,
    transport: InMemoryTransport | None = None,
    indicator: StatusIndicator | None = None,
    config: AgentConfig | None = None,
) -> tuple[SensorAgent, InMemoryTransport]:
    uplink = transport if transport is not None else InMemoryTransport()
    agent = SensorAgent(
        config if config is not None else _config(),
        sample=ScriptedSensor(clock, script),
        clock=clock,
        buffer=SqliteBufferStore(":memory:", 1000),
        transport=uplink,
        indicator=indicator,
    )
    return agent, uplink


def test_happy_cycle_buffers_and_publishes() -> None:
    clock = FakeClock()
    agent, transport = _agent(clock, [5.0])
    agent.run_cycle()
    assert agent.health.readings_ok == 1
    assert agent.health.published_readings == 1
    assert len(transport.published) == 1
    assert transport.published[0][0] == "aurora/v1/clinic/clinic-1/device/fridge-A/telemetry"


def test_sensor_error_is_counted_and_not_buffered() -> None:
    clock = FakeClock()
    agent, transport = _agent(clock, [OSError("bus error")])
    agent.run_cycle()
    assert agent.health.sensor_errors == 1
    assert agent.health.readings_ok == 0
    assert transport.published == []


def test_nan_reading_is_dropped() -> None:
    clock = FakeClock()
    agent, transport = _agent(clock, [math.nan])
    agent.run_cycle()
    assert agent.health.invalid_readings == 1
    assert agent.health.readings_ok == 0
    assert transport.published == []


def test_publish_failure_keeps_readings_then_backfills() -> None:
    clock = FakeClock()
    transport = InMemoryTransport(failing=True)
    agent, _ = _agent(clock, [5.0, 5.1, 5.2], transport=transport)

    agent.run_cycle()  # publish fails; reading stays buffered
    assert agent.health.publish_failures == 1
    assert agent.beacon().buffer_depth == 1

    transport.set_failing(False)
    agent.run_cycle()  # new reading + the backlog all drain in one batch
    assert agent.beacon().buffer_depth == 0
    published = transport.published[-1]
    assert published[0].endswith("/telemetry")


def test_excursion_drives_the_indicator_to_alarm() -> None:
    clock = FakeClock()
    pins = [FakeGpioPin() for _ in range(4)]
    indicator = StatusIndicator(*pins)
    agent, _ = _agent(clock, [12.0, 12.0, 12.0], indicator=indicator)

    agent.run(3)  # sustained out-of-range; dwell 0.1 min = 6 s < 30 s interval
    assert agent.excursion_state is ExcursionState.EXCURSION
    assert indicator.state is IndicatorState.ALARM


def test_clock_step_is_detected() -> None:
    clock = FakeClock()
    agent, _ = _agent(clock, [5.0, 5.0])
    agent.run_cycle()
    clock.step_wall(3600.0)  # RTC jumps an hour, monotonic does not
    agent.run_cycle()
    assert agent.health.clock_steps == 1
    assert agent.health.last_skew_seconds >= 3600.0
