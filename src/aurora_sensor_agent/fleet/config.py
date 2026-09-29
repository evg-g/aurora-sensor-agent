"""The ``fleet.yaml`` schema: devices, fault profiles, and staged-rollout cohorts.

Validated at load time (pydantic) so a typo in a cohort's device list, or a duplicate device id,
fails immediately with a clear message rather than half-way through a rollout.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator


class FaultProfile(str, Enum):
    """How a virtual device behaves, before and (optionally) after an update.

    ``flaky_uplink`` and ``dead_uplink`` model a network that drops some or all publishes;
    ``bad_sensor`` models a sensor that keeps raising read errors. A device whose
    ``profile_after_update`` is worse than its ``profile`` is how a bad rollout is simulated: the
    regression only shows up once the update is applied.
    """

    HEALTHY = "healthy"
    FLAKY_UPLINK = "flaky_uplink"
    DEAD_UPLINK = "dead_uplink"
    BAD_SENSOR = "bad_sensor"


class DeviceSpec(BaseModel):
    """One virtual device in the fleet."""

    id: str = Field(min_length=1)
    clinic_id: str = Field(min_length=1)
    setpoint_c: float = 5.0
    seed: int = 0
    profile: FaultProfile = FaultProfile.HEALTHY
    profile_after_update: FaultProfile | None = None
    firmware_version: str = "1.0.0"

    def effective_profile(self, *, updated: bool) -> FaultProfile:
        """The profile that applies now: the post-update one once updated, else the base one."""
        if updated and self.profile_after_update is not None:
            return self.profile_after_update
        return self.profile


class CohortSpec(BaseModel):
    """A rollout stage: the devices that get the update at this step (canary, 10%, fleet)."""

    name: str = Field(min_length=1)
    devices: list[str] = Field(min_length=1)


class RolloutPolicy(BaseModel):
    """When a staged rollout must halt itself.

    ``error_rate_threshold`` is how much a cohort's error rate may rise *above the pre-update
    baseline* before the rollout stops; ``max_error_rate`` is a hard cap regardless of baseline.
    """

    error_rate_threshold: float = Field(default=0.2, ge=0.0, le=1.0)
    max_error_rate: float = Field(default=0.5, ge=0.0, le=1.0)


class FleetConfig(BaseModel):
    """A whole fleet: its devices, the rollout cohorts, and the halt policy."""

    devices: list[DeviceSpec] = Field(min_length=1)
    cohorts: list[CohortSpec] = Field(default_factory=list)
    rollout: RolloutPolicy = Field(default_factory=RolloutPolicy)

    @model_validator(mode="after")
    def _check_ids(self) -> FleetConfig:
        ids = [d.id for d in self.devices]
        duplicates = {i for i in ids if ids.count(i) > 1}
        if duplicates:
            raise ValueError(f"duplicate device ids: {sorted(duplicates)}")
        known = set(ids)
        for cohort in self.cohorts:
            unknown = [d for d in cohort.devices if d not in known]
            if unknown:
                raise ValueError(f"cohort {cohort.name!r} references unknown devices: {unknown}")
        return self

    def device(self, device_id: str) -> DeviceSpec:
        for spec in self.devices:
            if spec.id == device_id:
                return spec
        raise KeyError(device_id)


def load_fleet_config(path: Path) -> FleetConfig:
    """Load and validate a ``fleet.yaml`` file."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return FleetConfig.model_validate(data)


__all__ = [
    "CohortSpec",
    "DeviceSpec",
    "FaultProfile",
    "FleetConfig",
    "RolloutPolicy",
    "load_fleet_config",
]
