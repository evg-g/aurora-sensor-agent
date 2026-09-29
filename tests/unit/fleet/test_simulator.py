"""Tests for the fleet simulator (virtual devices + run_fleet)."""

from __future__ import annotations

from aurora_sensor_agent.fleet.config import CohortSpec, DeviceSpec, FaultProfile, FleetConfig
from aurora_sensor_agent.fleet.simulator import VirtualClock, run_device, run_fleet


def test_healthy_device_publishes_with_zero_error_rate() -> None:
    spec = DeviceSpec(id="d1", clinic_id="c", profile=FaultProfile.HEALTHY, seed=1)

    result = run_device(spec, cycles=10)

    assert result.readings_ok == 10
    assert result.publish_failures == 0
    assert result.sensor_errors == 0
    assert result.published_readings == 10
    assert result.error_rate == 0.0
    assert result.buffer_depth == 0


def test_dead_uplink_device_has_max_error_rate() -> None:
    spec = DeviceSpec(id="d1", clinic_id="c", profile=FaultProfile.DEAD_UPLINK, seed=1)

    result = run_device(spec, cycles=10)

    assert result.publish_failures == 10
    assert result.error_rate == 1.0
    assert result.buffer_depth > 0  # nothing got acknowledged


def test_bad_sensor_device_records_read_errors() -> None:
    spec = DeviceSpec(id="d1", clinic_id="c", profile=FaultProfile.BAD_SENSOR, seed=3)

    result = run_device(spec, cycles=20)

    assert result.sensor_errors > 0
    assert result.readings_ok < 20
    assert result.error_rate > 0.0


def test_runs_are_deterministic() -> None:
    spec = DeviceSpec(id="d1", clinic_id="c", profile=FaultProfile.BAD_SENSOR, seed=7)

    first = run_device(spec, cycles=15)
    second = run_device(spec, cycles=15)

    assert first == second


def test_update_flag_selects_post_update_profile() -> None:
    spec = DeviceSpec(
        id="d1",
        clinic_id="c",
        profile=FaultProfile.HEALTHY,
        profile_after_update=FaultProfile.DEAD_UPLINK,
        seed=1,
    )

    before = run_device(spec, cycles=10, updated=False)
    after = run_device(spec, cycles=10, updated=True, firmware_version="2.0.0")

    assert before.error_rate == 0.0
    assert after.error_rate == 1.0
    assert after.firmware_version == "2.0.0"


def test_run_fleet_aggregates_all_devices() -> None:
    config = FleetConfig(
        devices=[
            DeviceSpec(id="a", clinic_id="c", profile=FaultProfile.HEALTHY, seed=1),
            DeviceSpec(id="b", clinic_id="c", profile=FaultProfile.DEAD_UPLINK, seed=2),
        ],
        cohorts=[CohortSpec(name="canary", devices=["a"])],
    )

    report = run_fleet(config, cycles=10)

    assert len(report.results) == 2
    # One device at 0.0, one at 1.0 -> mean 0.5.
    assert report.error_rate == 0.5
    assert "fleet error rate" in report.summary_table()


def test_virtual_clock_advances_without_blocking() -> None:
    clock = VirtualClock()
    start = clock.monotonic()
    clock.sleep(60.0)
    assert clock.monotonic() == start + 60.0
