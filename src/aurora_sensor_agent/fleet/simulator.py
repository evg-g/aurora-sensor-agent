"""Run many virtual devices at once and report their health.

Each virtual device is a *real* ``SensorAgent`` wired to the simulated fridge and sensor, so the
fleet exercises the same run loop the field code does — only the sensor bus and (by default) the
uplink are fakes. Time is driven by a ``VirtualClock`` that advances on ``sleep`` instead of
blocking, so a fleet of dozens of devices over hundreds of cycles finishes in milliseconds even when
a device is stuck in backoff after every failed publish.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from aurora_sensor_agent.agent import SensorAgent
from aurora_sensor_agent.config import AgentConfig, ThresholdPolicy
from aurora_sensor_agent.drivers.sht4x import Precision, Sht4xDriver
from aurora_sensor_agent.fleet.config import DeviceSpec, FaultProfile, FleetConfig
from aurora_sensor_agent.models import Reading
from aurora_sensor_agent.protocols import Transport
from aurora_sensor_agent.sim.i2c import SimulatedSht4xBus
from aurora_sensor_agent.sim.thermal import ThermalModel

_FLAKY_DROP_PROBABILITY = 0.4
_BAD_SENSOR_ERROR_PROBABILITY = 0.5


class VirtualClock:
    """A ``Clock`` that advances on ``sleep`` instead of blocking — deterministic and instant."""

    def __init__(self, start: datetime | None = None) -> None:
        self._wall = start if start is not None else datetime(2026, 1, 1, tzinfo=UTC)
        self._mono = 0.0

    def now(self) -> datetime:
        return self._wall

    def monotonic(self) -> float:
        return self._mono

    def sleep(self, seconds: float) -> None:
        self._mono += seconds
        self._wall += timedelta(seconds=seconds)


class SimUplink:
    """A ``Transport`` that drops a configurable fraction of publishes, seeded and deterministic."""

    def __init__(self, *, fail_probability: float = 0.0, seed: int = 0) -> None:
        self._p = fail_probability
        self._rng = random.Random(seed)
        self.delivered = 0
        self.failed = 0

    def publish(self, topic: str, payload: bytes) -> None:
        if self._p > 0.0 and self._rng.random() < self._p:
            self.failed += 1
            raise ConnectionError("simulated uplink drop")
        self.delivered += 1

    def close(self) -> None:
        return None


@dataclass(frozen=True, slots=True)
class DeviceRunResult:
    """The outcome of running one virtual device for a number of cycles."""

    device_id: str
    firmware_version: str
    cycles: int
    readings_ok: int
    sensor_errors: int
    publish_failures: int
    published_readings: int
    buffer_depth: int
    excursion_state: str

    @property
    def error_rate(self) -> float:
        """Failures (sensor read or publish) per cycle, clamped to [0, 1]."""
        if self.cycles == 0:
            return 0.0
        return min(1.0, (self.sensor_errors + self.publish_failures) / self.cycles)


@dataclass(frozen=True, slots=True)
class FleetReport:
    """Per-device results plus the fleet-wide error rate."""

    results: list[DeviceRunResult]

    @property
    def error_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.error_rate for r in self.results) / len(self.results)

    def summary_table(self) -> str:
        header = (
            f"{'device':<16}{'fw':>8}{'ok':>6}{'sensErr':>9}{'pubFail':>9}"
            f"{'buffer':>8}{'excursion':>12}{'errRate':>9}"
        )
        lines = [header, "-" * len(header)]
        for r in self.results:
            lines.append(
                f"{r.device_id:<16}{r.firmware_version:>8}{r.readings_ok:>6}{r.sensor_errors:>9}"
                f"{r.publish_failures:>9}{r.buffer_depth:>8}{r.excursion_state:>12}"
                f"{r.error_rate:>9.2f}"
            )
        lines.append(f"\nfleet error rate: {self.error_rate:.3f}  ({len(self.results)} devices)")
        return "\n".join(lines)


def _sampler(spec: DeviceSpec, profile: FaultProfile, clock: VirtualClock) -> Callable[[], Reading]:
    """Build the per-device sample function; BAD_SENSOR wraps it to raise read errors."""
    bus = SimulatedSht4xBus(clock, ThermalModel(seed=spec.seed, setpoint_c=spec.setpoint_c))
    driver = Sht4xDriver(bus, clock)

    if profile is FaultProfile.BAD_SENSOR:
        rng = random.Random(spec.seed ^ 0xBAD)

        def sample() -> Reading:
            if rng.random() < _BAD_SENSOR_ERROR_PROBABILITY:
                raise OSError("simulated sensor fault")
            return driver.measure(Precision.HIGH)

        return sample

    return lambda: driver.measure(Precision.HIGH)


def _uplink_for(profile: FaultProfile, seed: int) -> Transport:
    if profile is FaultProfile.FLAKY_UPLINK:
        return SimUplink(fail_probability=_FLAKY_DROP_PROBABILITY, seed=seed)
    if profile is FaultProfile.DEAD_UPLINK:
        return SimUplink(fail_probability=1.0, seed=seed)
    return SimUplink(fail_probability=0.0, seed=seed)


def run_device(
    spec: DeviceSpec,
    cycles: int,
    *,
    updated: bool = False,
    firmware_version: str | None = None,
    thresholds: ThresholdPolicy | None = None,
    transport: Transport | None = None,
) -> DeviceRunResult:
    """Run one virtual device for ``cycles`` cycles and return its health result.

    When ``transport`` is given (e.g. a real MQTT transport for SIL) it is used as-is and only the
    sensor honours the fault profile; otherwise a simulated uplink is built from the effective
    profile so offline fleet/rollout runs can model network faults.
    """
    profile = spec.effective_profile(updated=updated)
    clock = VirtualClock()
    sample = _sampler(spec, profile, clock)
    uplink = transport if transport is not None else _uplink_for(profile, spec.seed)
    fw = firmware_version if firmware_version is not None else spec.firmware_version

    config = AgentConfig(
        device_id=spec.id,
        clinic_id=spec.clinic_id,
        firmware_version=fw,
        sample_interval_seconds=30.0,
        thresholds=thresholds if thresholds is not None else ThresholdPolicy(),
        buffer_path=":memory:",
    )
    agent = SensorAgent(
        config,
        sample=sample,
        clock=clock,
        buffer=_MemoryBuffer(),
        transport=uplink,
    )
    agent.run(cycles)
    beacon = agent.beacon()
    return DeviceRunResult(
        device_id=spec.id,
        firmware_version=fw,
        cycles=beacon.cycles,
        readings_ok=beacon.readings_ok,
        sensor_errors=beacon.sensor_errors,
        publish_failures=beacon.publish_failures,
        published_readings=beacon.published_readings,
        buffer_depth=beacon.buffer_depth,
        excursion_state=beacon.excursion_state,
    )


def run_fleet(
    config: FleetConfig,
    cycles: int,
    *,
    updated_ids: frozenset[str] = frozenset(),
    transport_factory: Callable[[DeviceSpec], Transport] | None = None,
    firmware_by_id: dict[str, str] | None = None,
) -> FleetReport:
    """Run every device in the fleet for ``cycles`` cycles and collect a report."""
    firmware_by_id = firmware_by_id or {}
    results = [
        run_device(
            spec,
            cycles,
            updated=spec.id in updated_ids,
            firmware_version=firmware_by_id.get(spec.id),
            transport=transport_factory(spec) if transport_factory is not None else None,
        )
        for spec in config.devices
    ]
    return FleetReport(results=results)


class _MemoryBuffer:
    """A tiny in-RAM BufferStore for the simulator (SqliteBufferStore(':memory:') also works, but
    this avoids a SQLite connection per device when running a large fleet)."""

    def __init__(self) -> None:
        self._rows: dict[int, str] = {}
        self._next = 1

    def append(self, reading_json: str) -> int:
        row_id = self._next
        self._next += 1
        self._rows[row_id] = reading_json
        return row_id

    def pending(self, limit: int) -> list[tuple[int, str]]:
        return [(rid, self._rows[rid]) for rid in sorted(self._rows)][:limit]

    def acknowledge(self, row_ids: list[int]) -> None:
        for rid in row_ids:
            self._rows.pop(rid, None)

    def depth(self) -> int:
        return len(self._rows)


__all__ = [
    "DeviceRunResult",
    "FleetReport",
    "SimUplink",
    "VirtualClock",
    "run_device",
    "run_fleet",
]
