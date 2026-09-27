"""Soak / time tier: seven simulated days compressed into a fraction of a second.

What it proves, and why each matters:

- **No memory growth** — the agent runs for a week of samples; ``tracemalloc`` shows live memory
  does not creep. A per-cycle leak (an unbounded list, a cache that never evicts) would show here.
- **No buffer leak** — during a two-day network outage the store-and-forward buffer fills but never
  exceeds capacity (ring-buffer eviction holds), and drains to empty when the uplink returns.
- **Correct across a DST change** — the run spans the European spring-forward. The device stamps UTC
  and the excursion timers use elapsed time, so a local-clock DST jump changes nothing — the whole
  reason the timer must not use a local wall clock (ADR 0003). Every cycle still yields a reading
  across the boundary.

Everything runs on a ``FakeClock``, so "seven days" is instant and deterministic.
"""

from __future__ import annotations

import gc
import tracemalloc
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from aurora_sensor_agent.agent import SensorAgent
from aurora_sensor_agent.buffer.sqlite import SqliteBufferStore
from aurora_sensor_agent.config import AgentConfig
from aurora_sensor_agent.drivers.sht4x import Precision, Sht4xDriver
from aurora_sensor_agent.sim.i2c import SimulatedSht4xBus
from aurora_sensor_agent.sim.thermal import ThermalModel
from aurora_sensor_agent.transport.memory import InMemoryTransport
from tests.fakes.clock import FakeClock

_INTERVAL_S = 300.0
_DAYS = 7
_CYCLES = int(_DAYS * 24 * 3600 / _INTERVAL_S)  # 2016
_START = datetime(2026, 3, 27, 0, 0, tzinfo=UTC)  # two days before EU DST (2026-03-29)
_CAPACITY = 500


def test_seven_day_soak() -> None:
    clock = FakeClock(start=_START)
    config = AgentConfig(
        device_id="fridge-A",
        clinic_id="clinic-1",
        sample_interval_seconds=_INTERVAL_S,
        median_window=5,
        buffer_capacity=_CAPACITY,
        batch_max_readings=100,
    )
    buffer = SqliteBufferStore(":memory:", _CAPACITY)
    transport = InMemoryTransport(retain=False)  # do not accumulate, or the transport itself grows
    driver = Sht4xDriver(SimulatedSht4xBus(clock, ThermalModel(seed=1, setpoint_c=5.0)), clock)
    agent = SensorAgent(
        config,
        sample=lambda: driver.measure(Precision.HIGH),
        clock=clock,
        buffer=buffer,
        transport=transport,
    )

    # Warm up so first-touch allocations (module caches, sqlite pages) are already made.
    warmup = 200
    for _ in range(warmup):
        agent.run_cycle()
        clock.sleep(_INTERVAL_S)

    gc.collect()
    tracemalloc.start()
    base_current, _ = tracemalloc.get_traced_memory()

    outage_start = warmup + 200
    outage_end = outage_start + int(2 * 24 * 3600 / _INTERVAL_S)  # two days offline
    max_depth = 0
    for i in range(warmup, _CYCLES):
        if i == outage_start:
            transport.set_failing(True)
        elif i == outage_end:
            transport.set_failing(False)
        agent.run_cycle()
        max_depth = max(max_depth, buffer.depth())
        clock.sleep(_INTERVAL_S)

    gc.collect()
    end_current, _ = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Every cycle produced a valid reading (the sim never emits a bad sample here).
    assert agent.health.readings_ok == _CYCLES

    # Buffer stayed bounded through the outage, actually filled (eviction ran), then drained.
    assert max_depth == _CAPACITY
    assert buffer.evicted_total > 0
    assert buffer.depth() == 0

    # Live memory did not creep over ~1800 cycles of running.
    assert end_current - base_current < 1_000_000  # < 1 MB drift

    # The run really did cross a DST boundary in a European clinic timezone.
    tz = ZoneInfo("Europe/Amsterdam")
    first_offset = _START.astimezone(tz).utcoffset()
    last_offset = (_START + timedelta(seconds=_CYCLES * _INTERVAL_S)).astimezone(tz).utcoffset()
    assert first_offset != last_offset
