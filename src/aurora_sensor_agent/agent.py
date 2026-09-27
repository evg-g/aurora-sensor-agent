"""The agent run loop: everything wired together, one cycle at a time.

A cycle is the whole device behaviour in order:

1. **skew check** — compare how far the wall clock moved against the monotonic clock; a big gap
   means the RTC was stepped (NTP), so flag it.
2. **sample** — take a reading from the sensor; a bus/CRC fault is counted and the cycle ends.
3. **condition** — apply the calibration offset, reject a NaN/out-of-range sample, and feed the
   median-filtered temperature to the excursion machine.
4. **indicate** — drive the LED/buzzer from the excursion state.
5. **buffer** — write the reading to the store-and-forward buffer (a full disk is flagged, not
   fatal).
6. **drain** — batch the buffered readings and publish them; on failure, back off and leave them
   buffered for the next cycle (at-least-once delivery).

The loop takes an injected ``Clock``, so ``run`` over seven simulated days finishes in milliseconds
under a ``FakeClock`` — which is what the soak test relies on. No real sleep, no real wall clock.
"""

from __future__ import annotations

import logging
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from aurora_sensor_agent.buffer.sqlite import SqliteBufferStore
from aurora_sensor_agent.config import AgentConfig
from aurora_sensor_agent.logic.backoff import Backoff
from aurora_sensor_agent.logic.batch import build_batches
from aurora_sensor_agent.logic.excursion import ExcursionDetector, ExcursionState
from aurora_sensor_agent.logic.filter import MedianFilter, calibrate, is_valid_reading
from aurora_sensor_agent.logic.indicator import StatusIndicator
from aurora_sensor_agent.models import Reading
from aurora_sensor_agent.protocol.crc import CrcError
from aurora_sensor_agent.protocols import BufferStore, Clock, Transport
from aurora_sensor_agent.serde import reading_to_json
from aurora_sensor_agent.transport.memory import InMemoryTransport

_log = logging.getLogger("aurora_sensor_agent.agent")

# Sensor-read failures the driver may raise; each is transient and just ends the cycle.
_SENSOR_ERRORS = (OSError, CrcError, ValueError)


@dataclass
class AgentHealth:
    """Mutable counters the agent keeps, surfaced in the health beacon."""

    cycles: int = 0
    readings_ok: int = 0
    sensor_errors: int = 0
    invalid_readings: int = 0
    buffer_write_failures: int = 0
    publish_failures: int = 0
    published_batches: int = 0
    published_readings: int = 0
    clock_steps: int = 0
    last_skew_seconds: float = 0.0
    last_measured_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class HealthBeacon:
    """A point-in-time snapshot the agent would publish to the health topic."""

    device_id: str
    firmware_version: str
    uptime_seconds: float
    buffer_depth: int
    buffer_evicted: int
    excursion_state: str
    cycles: int
    readings_ok: int
    sensor_errors: int
    invalid_readings: int
    buffer_write_failures: int
    publish_failures: int
    published_batches: int
    published_readings: int
    clock_steps: int
    last_skew_seconds: float


def telemetry_topic(clinic_id: str, device_id: str) -> str:
    """The MQTT telemetry topic for a device (used by the transport in milestone 10)."""
    return f"aurora/v1/clinic/{clinic_id}/device/{device_id}/telemetry"


class SensorAgent:
    """Composes the sensor, the logic layer, the buffer, and the transport into a run loop."""

    def __init__(
        self,
        config: AgentConfig,
        *,
        sample: Callable[[], Reading],
        clock: Clock,
        buffer: BufferStore,
        transport: Transport,
        indicator: StatusIndicator | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self._config = config
        self._sample = sample
        self._clock = clock
        self._buffer = buffer
        self._transport = transport
        self._indicator = indicator
        self._filter = MedianFilter(config.median_window)
        self._excursion = ExcursionDetector(config.thresholds)
        self._backoff = Backoff(
            base_seconds=config.backoff.base_seconds,
            factor=config.backoff.factor,
            max_seconds=config.backoff.max_seconds,
            jitter=config.backoff.jitter,
            rng=rng if rng is not None else random.Random(0),
        )
        self._topic = telemetry_topic(config.clinic_id, config.device_id)
        self.health = AgentHealth()
        self._start_monotonic = clock.monotonic()
        self._last_wall: datetime | None = None
        self._last_monotonic: float | None = None

    @property
    def excursion_state(self) -> ExcursionState:
        return self._excursion.state

    def run_cycle(self) -> None:
        """Run one sample→publish cycle. An expected fault is recorded, not raised."""
        self.health.cycles += 1
        self._check_clock_step()

        try:
            raw = self._sample()
        except _SENSOR_ERRORS:
            self.health.sensor_errors += 1
            _log.warning("sensor read failed", extra={"device_id": self._config.device_id})
            return

        reading = calibrate(raw, self._config.calibration_offset_c)
        if not is_valid_reading(reading):
            self.health.invalid_readings += 1
            _log.warning("dropped invalid reading", extra={"device_id": self._config.device_id})
            return

        smoothed = self._filter.push(reading.temperature_c)
        self._excursion.update(smoothed, reading.measured_at)
        if self._indicator is not None:
            self._indicator.apply(self._excursion.state)

        self.health.readings_ok += 1
        self.health.last_measured_at = reading.measured_at

        try:
            self._buffer.append(reading_to_json(reading))
        except OSError:
            # Disk full or a transient write error: flag it and drop this reading, but still try to
            # drain — uploading what is already buffered is what frees the space back up.
            self.health.buffer_write_failures += 1
            _log.error("buffer write failed", extra={"device_id": self._config.device_id})

        self._drain()

    def run(self, cycles: int) -> None:
        """Run ``cycles`` cycles, sleeping the sample interval between them (instant on a fake)."""
        for index in range(cycles):
            self.run_cycle()
            if index < cycles - 1:
                self._clock.sleep(self._config.sample_interval_seconds)

    def beacon(self) -> HealthBeacon:
        """Build the current health snapshot."""
        return HealthBeacon(
            device_id=self._config.device_id,
            firmware_version=self._config.firmware_version,
            uptime_seconds=self._clock.monotonic() - self._start_monotonic,
            buffer_depth=self._buffer.depth(),
            buffer_evicted=getattr(self._buffer, "evicted_total", 0),
            excursion_state=self._excursion.state.value,
            cycles=self.health.cycles,
            readings_ok=self.health.readings_ok,
            sensor_errors=self.health.sensor_errors,
            invalid_readings=self.health.invalid_readings,
            buffer_write_failures=self.health.buffer_write_failures,
            publish_failures=self.health.publish_failures,
            published_batches=self.health.published_batches,
            published_readings=self.health.published_readings,
            clock_steps=self.health.clock_steps,
            last_skew_seconds=self.health.last_skew_seconds,
        )

    def _drain(self) -> None:
        """Publish buffered readings until the buffer is empty or a publish fails."""
        while True:
            pending = self._buffer.pending(self._config.batch_max_readings)
            if not pending:
                break
            batch = build_batches(
                pending,
                device_id=self._config.device_id,
                max_readings=self._config.batch_max_readings,
            )[0]
            try:
                self._transport.publish(self._topic, batch.payload)
            except (OSError, ConnectionError):
                self.health.publish_failures += 1
                self._clock.sleep(self._backoff.next_delay())
                return  # leave everything buffered; retry next cycle
            self._buffer.acknowledge(batch.row_ids)
            self.health.published_batches += 1
            self.health.published_readings += len(batch.row_ids)
        self._backoff.reset()

    def _check_clock_step(self) -> None:
        """Flag a wall-clock step: the wall clock and the monotonic clock should move together."""
        now_wall = self._clock.now()
        now_monotonic = self._clock.monotonic()
        if self._last_wall is not None and self._last_monotonic is not None:
            wall_delta = (now_wall - self._last_wall).total_seconds()
            monotonic_delta = now_monotonic - self._last_monotonic
            skew = abs(wall_delta - monotonic_delta)
            self.health.last_skew_seconds = skew
            if skew > self._config.max_clock_skew_seconds:
                self.health.clock_steps += 1
                _log.warning(
                    "clock step detected",
                    extra={"device_id": self._config.device_id, "skew_s": skew},
                )
        self._last_wall = now_wall
        self._last_monotonic = now_monotonic


def assemble_agent(
    config: AgentConfig,
    *,
    sample: Callable[[], Reading],
    clock: Clock,
    transport: Transport | None = None,
    buffer: BufferStore | None = None,
    indicator: StatusIndicator | None = None,
    rng: random.Random | None = None,
) -> SensorAgent:
    """Build a ``SensorAgent`` with default buffer/transport, for the CLI and soak test."""
    if buffer is not None:
        store: BufferStore = buffer
    else:
        store = SqliteBufferStore(config.buffer_path, config.buffer_capacity)
    uplink = transport if transport is not None else InMemoryTransport()
    return SensorAgent(
        config,
        sample=sample,
        clock=clock,
        buffer=store,
        transport=uplink,
        indicator=indicator,
        rng=rng,
    )


__all__ = [
    "AgentHealth",
    "HealthBeacon",
    "SensorAgent",
    "assemble_agent",
    "telemetry_topic",
]
