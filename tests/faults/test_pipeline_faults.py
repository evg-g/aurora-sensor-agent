"""Fault tier: the higher-layer faults (NaN, disk full, clock jump).

The chip/bus faults (bad CRC, NACK, timeout, short read, power loss, stuck) are covered in
``tests/unit/sim/test_faults.py``. This module covers the three faults above the wire, and asserts
the property the whole design turns on: **a fault never loses already-buffered data or produces a
duplicate on the server.**
"""

from __future__ import annotations

from aurora_sensor_agent.agent import SensorAgent
from aurora_sensor_agent.buffer.sqlite import SqliteBufferStore
from aurora_sensor_agent.config import AgentConfig, ThresholdPolicy
from aurora_sensor_agent.logic.batch import build_batches
from aurora_sensor_agent.logic.excursion import ExcursionDetector, ExcursionState
from aurora_sensor_agent.models import Reading
from aurora_sensor_agent.protocols import Clock
from aurora_sensor_agent.serde import reading_to_json
from aurora_sensor_agent.sim.pipeline_faults import (
    DiskFullError,
    FaultingBufferStore,
    PipelineFault,
    nan_reading,
)
from aurora_sensor_agent.transport.memory import InMemoryTransport
from tests.fakes.clock import FakeClock


def _config() -> AgentConfig:
    return AgentConfig(
        device_id="fridge-A",
        clinic_id="clinic-1",
        median_window=1,
        thresholds=ThresholdPolicy(
            min_temperature_c=2.0, max_temperature_c=8.0, dwell_minutes=0.1, recovery_minutes=0.1
        ),
    )


def _reading(clock: Clock, temperature_c: float) -> Reading:
    return Reading(
        temperature_c=temperature_c,
        humidity_pct=45.0,
        measured_at=clock.now(),
        raw_temperature=0,
        raw_humidity=0,
    )


def test_every_pipeline_fault_has_coverage() -> None:
    # Guard: if a new fault is added to the catalogue, this list must grow (and a test with it).
    assert {f.value for f in PipelineFault} == {"nan", "disk_full", "clock_jump"}


# ---- NAN -----------------------------------------------------------------------------------


def test_nan_reading_is_rejected_and_not_buffered() -> None:
    clock = FakeClock()
    buffer = SqliteBufferStore(":memory:", 100)
    agent = SensorAgent(
        _config(),
        sample=lambda: nan_reading(clock.now()),
        clock=clock,
        buffer=buffer,
        transport=InMemoryTransport(),
    )
    agent.run_cycle()
    assert agent.health.invalid_readings == 1
    assert buffer.depth() == 0  # a poisoned sample never enters the buffer


# ---- DISK_FULL -----------------------------------------------------------------------------


def test_disk_full_is_flagged_and_does_not_crash() -> None:
    clock = FakeClock()
    inner = SqliteBufferStore(":memory:", 100)
    faulting = FaultingBufferStore(inner, fail_at=0, fail_forever=True)
    agent = SensorAgent(
        _config(),
        sample=lambda: _reading(clock, 5.0),
        clock=clock,
        buffer=faulting,
        transport=InMemoryTransport(),
    )
    agent.run_cycle()
    assert agent.health.buffer_write_failures == 1


def test_disk_full_does_not_lose_already_buffered_data() -> None:
    clock = FakeClock()
    inner = SqliteBufferStore(":memory:", 100)
    inner.append(reading_to_json(_reading(clock, 4.0)))  # one reading already safely buffered
    faulting = FaultingBufferStore(inner, fail_at=0, fail_forever=True)
    transport = InMemoryTransport()
    agent = SensorAgent(
        _config(),
        sample=lambda: _reading(clock, 5.0),
        clock=clock,
        buffer=faulting,
        transport=transport,
    )
    agent.run_cycle()
    # The new write failed, but the pre-existing reading was still drained to the transport.
    assert agent.health.buffer_write_failures == 1
    assert inner.depth() == 0
    assert len(transport.published) == 1


def test_transient_disk_error_recovers_on_next_write() -> None:
    inner = SqliteBufferStore(":memory:", 100)
    faulting = FaultingBufferStore(inner, fail_at=0, fail_forever=False)
    try:
        faulting.append("first")  # this one fails
        raise AssertionError("expected DiskFullError")
    except DiskFullError:
        pass
    row_id = faulting.append("second")  # transient: now it works
    assert row_id > 0
    assert inner.depth() == 1


# ---- CLOCK_JUMP ----------------------------------------------------------------------------


def test_clock_jump_does_not_produce_a_spurious_excursion() -> None:
    policy = ThresholdPolicy(
        min_temperature_c=2.0, max_temperature_c=8.0, dwell_minutes=15.0, recovery_minutes=10.0
    )
    detector = ExcursionDetector(policy)
    clock = FakeClock()
    # Raise an excursion normally.
    for _ in range(5):
        detector.update(12.0, clock.now())
        clock.advance(300.0)
    assert detector.state is ExcursionState.EXCURSION
    # Now the RTC steps backwards an hour; the machine must not emit anything or corrupt its state.
    clock.step_wall(-3600.0)
    event = detector.update(12.0, clock.now())
    assert event is None
    assert detector.state is ExcursionState.EXCURSION


def test_retried_batch_reuses_idempotency_key_so_server_can_dedupe() -> None:
    # The property that makes at-least-once safe: the same rows always hash to the same key.
    rows = [(1, '{"n":1}'), (2, '{"n":2}'), (3, '{"n":3}')]
    first = build_batches(rows, device_id="fridge-A", max_readings=10)[0]
    retry = build_batches(rows, device_id="fridge-A", max_readings=10)[0]
    assert first.idempotency_key == retry.idempotency_key
