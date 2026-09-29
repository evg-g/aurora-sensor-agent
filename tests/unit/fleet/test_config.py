"""Tests for the fleet.yaml schema."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from aurora_sensor_agent.fleet.config import (
    CohortSpec,
    DeviceSpec,
    FaultProfile,
    FleetConfig,
    load_fleet_config,
)


def test_loads_the_repo_fleet_yaml() -> None:
    config = load_fleet_config(Path(__file__).resolve().parents[3] / "fleet.yaml")
    assert len(config.devices) == 10
    assert [c.name for c in config.cohorts] == ["canary", "ten_percent", "fleet"]
    assert config.device("dev-bergen-05").profile is FaultProfile.FLAKY_UPLINK


def test_duplicate_device_ids_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate device ids"):
        FleetConfig(
            devices=[
                DeviceSpec(id="d1", clinic_id="c"),
                DeviceSpec(id="d1", clinic_id="c"),
            ]
        )


def test_cohort_referencing_unknown_device_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown devices"):
        FleetConfig(
            devices=[DeviceSpec(id="d1", clinic_id="c")],
            cohorts=[CohortSpec(name="canary", devices=["ghost"])],
        )


def test_effective_profile_switches_on_update() -> None:
    spec = DeviceSpec(
        id="d1",
        clinic_id="c",
        profile=FaultProfile.HEALTHY,
        profile_after_update=FaultProfile.DEAD_UPLINK,
    )
    assert spec.effective_profile(updated=False) is FaultProfile.HEALTHY
    assert spec.effective_profile(updated=True) is FaultProfile.DEAD_UPLINK


def test_effective_profile_defaults_to_base_when_no_post_update() -> None:
    spec = DeviceSpec(id="d1", clinic_id="c", profile=FaultProfile.FLAKY_UPLINK)
    assert spec.effective_profile(updated=True) is FaultProfile.FLAKY_UPLINK
