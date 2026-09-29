"""Tests for the staged OTA rollout (canary -> 10% -> fleet, with auto-halt)."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from aurora_sensor_agent.fleet.config import CohortSpec, DeviceSpec, FaultProfile, FleetConfig
from aurora_sensor_agent.fleet.rollout import StagedRollout
from aurora_sensor_agent.ota import OtaVerificationError, canonical_payload_bytes


def _config(*, bad_build: bool) -> FleetConfig:
    post = FaultProfile.DEAD_UPLINK if bad_build else None
    return FleetConfig(
        devices=[
            DeviceSpec(id="c1", clinic_id="c", seed=1, profile_after_update=post),
            DeviceSpec(id="t1", clinic_id="c", seed=2, profile_after_update=post),
            DeviceSpec(id="f1", clinic_id="c", seed=3, profile_after_update=post),
            DeviceSpec(id="f2", clinic_id="c", seed=4, profile_after_update=post),
        ],
        cohorts=[
            CohortSpec(name="canary", devices=["c1"]),
            CohortSpec(name="ten_percent", devices=["t1"]),
            CohortSpec(name="fleet", devices=["f1", "f2"]),
        ],
    )


def test_healthy_update_completes_all_cohorts() -> None:
    rollout = StagedRollout(_config(bad_build=False), cycles=10)

    result = rollout.run("1.1.0")

    assert result.completed is True
    assert result.halted is False
    assert [c.name for c in result.cohorts] == ["canary", "ten_percent", "fleet"]
    assert all(c.healthy for c in result.cohorts)


def test_bad_build_halts_at_canary() -> None:
    rollout = StagedRollout(_config(bad_build=True), cycles=10)

    result = rollout.run("1.1.0")

    assert result.halted is True
    assert result.halted_at == "canary"
    assert len(result.cohorts) == 1  # stopped before 10% / fleet got the build
    assert result.updated_device_ids == ["c1"]
    assert "HALTED" in result.summary()


def test_rollout_requires_cohorts() -> None:
    config = FleetConfig(devices=[DeviceSpec(id="a", clinic_id="c")])
    with pytest.raises(ValueError, match="no cohorts"):
        StagedRollout(config)


def _signed_manifest(artifact: Path, version: str, key: Ed25519PrivateKey) -> str:
    payload = {
        "version": version,
        "artifact": artifact.name,
        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "size": artifact.stat().st_size,
        "released_at": "2026-09-28T00:00:00+00:00",
    }
    signature = key.sign(canonical_payload_bytes(payload))
    return json.dumps(
        {
            "payload": payload,
            "signature": base64.b64encode(signature).decode(),
            "algorithm": "ed25519",
        }
    )


def test_run_verified_verifies_then_rolls_out(tmp_path: Path) -> None:
    key = Ed25519PrivateKey.generate()
    public_pem = key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    artifact = tmp_path / "agent-1.2.0.whl"
    artifact.write_bytes(b"good-build")
    manifest = _signed_manifest(artifact, "1.2.0", key)

    rollout = StagedRollout(_config(bad_build=False), cycles=8)
    result = rollout.run_verified(manifest, public_pem, artifact, current_version="1.0.0")

    assert result.version == "1.2.0"
    assert result.completed is True


def test_run_verified_refuses_tampered_manifest(tmp_path: Path) -> None:
    key = Ed25519PrivateKey.generate()
    public_pem = key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    artifact = tmp_path / "agent-1.2.0.whl"
    artifact.write_bytes(b"good-build")
    document = json.loads(_signed_manifest(artifact, "1.2.0", key))
    document["payload"]["version"] = "9.9.9"  # tamper after signing

    rollout = StagedRollout(_config(bad_build=False), cycles=8)
    with pytest.raises(OtaVerificationError):
        rollout.run_verified(json.dumps(document), public_pem, artifact, current_version="1.0.0")
