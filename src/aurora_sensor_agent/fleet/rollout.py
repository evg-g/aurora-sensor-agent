"""Staged rollout: push a verified update canary → 10% → fleet, and halt if error rate rises.

Shipping an update to every device at once means a bad build takes down the whole cold chain before
anyone notices. A staged rollout limits the blast radius: update a tiny **canary** cohort first,
watch its error rate, then a larger **10%** cohort, then the **fleet** — and stop the moment a
cohort's error rate climbs past the policy threshold. The remaining cohorts never get the bad build,
and the already-updated ones are flagged for rollback.

The error-rate signal here comes from the fleet simulator (failed sensor reads + failed publishes
per cycle). In production it would come from the real fleet's health beacons; the shape of the
decision is the same. The rollback path is documented in ``docs/OTA_ROLLOUT.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aurora_sensor_agent.fleet.config import FleetConfig
from aurora_sensor_agent.fleet.simulator import FleetReport, run_device, run_fleet
from aurora_sensor_agent.ota import prepare_update


@dataclass(frozen=True, slots=True)
class CohortResult:
    """How one cohort fared after the update was applied to it."""

    name: str
    device_ids: list[str]
    error_rate: float
    baseline_error_rate: float
    healthy: bool
    report: FleetReport


@dataclass(frozen=True, slots=True)
class RolloutResult:
    """The outcome of a whole staged rollout."""

    version: str
    baseline_error_rate: float
    cohorts: list[CohortResult]
    halted: bool
    halted_at: str | None

    @property
    def completed(self) -> bool:
        return not self.halted

    @property
    def updated_device_ids(self) -> list[str]:
        """Devices that received the update (across every cohort that ran) — the rollback set."""
        ids: list[str] = []
        for cohort in self.cohorts:
            ids.extend(cohort.device_ids)
        return ids

    def summary(self) -> str:
        lines = [
            f"OTA rollout of version {self.version}",
            f"baseline error rate: {self.baseline_error_rate:.3f}",
            "",
        ]
        for cohort in self.cohorts:
            verdict = "OK" if cohort.healthy else "HALT"
            lines.append(
                f"  [{verdict:>4}] {cohort.name:<12} "
                f"devices={len(cohort.device_ids):>2} "
                f"error_rate={cohort.error_rate:.3f} "
                f"(baseline {cohort.baseline_error_rate:.3f})"
            )
        lines.append("")
        if self.halted:
            lines.append(
                f"HALTED at cohort {self.halted_at!r}. Roll back: {self.updated_device_ids}."
            )
        else:
            lines.append("Completed: all cohorts within the error-rate policy.")
        return "\n".join(lines)


class StagedRollout:
    """Drive a staged rollout across the cohorts in a ``fleet.yaml``."""

    def __init__(self, config: FleetConfig, *, cycles: int = 30) -> None:
        if not config.cohorts:
            raise ValueError("fleet config has no cohorts to roll out to")
        self._config = config
        self._cycles = cycles

    def run(self, version: str) -> RolloutResult:
        """Apply ``version`` cohort by cohort, halting if a cohort's error rate rises too far."""
        policy = self._config.rollout
        baseline = run_fleet(self._config, self._cycles).error_rate

        cohorts: list[CohortResult] = []
        halted = False
        halted_at: str | None = None

        for cohort in self._config.cohorts:
            results = [
                run_device(
                    self._config.device(device_id),
                    self._cycles,
                    updated=True,
                    firmware_version=version,
                )
                for device_id in cohort.devices
            ]
            report = FleetReport(results=results)
            rate = report.error_rate
            healthy = (
                rate <= policy.max_error_rate and (rate - baseline) <= policy.error_rate_threshold
            )
            cohorts.append(
                CohortResult(
                    name=cohort.name,
                    device_ids=list(cohort.devices),
                    error_rate=rate,
                    baseline_error_rate=baseline,
                    healthy=healthy,
                    report=report,
                )
            )
            if not healthy:
                halted = True
                halted_at = cohort.name
                break

        return RolloutResult(
            version=version,
            baseline_error_rate=baseline,
            cohorts=cohorts,
            halted=halted,
            halted_at=halted_at,
        )

    def run_verified(
        self,
        manifest_json: str | bytes,
        public_key_pem: bytes,
        artifact_path: Path,
        current_version: str,
    ) -> RolloutResult:
        """Verify the OTA manifest first (signature + integrity + direction), then roll it out."""
        payload = prepare_update(manifest_json, public_key_pem, artifact_path, current_version)
        return self.run(payload.version)


__all__ = ["CohortResult", "RolloutResult", "StagedRollout"]
