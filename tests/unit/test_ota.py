"""Unit tests for OTA manifest verification — the security-critical part of the update flow."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from aurora_sensor_agent.ota import (
    OtaError,
    OtaVerificationError,
    canonical_payload_bytes,
    is_newer,
    parse_version,
    prepare_update,
    verify_artifact,
    verify_manifest,
)


def _keypair() -> tuple[Ed25519PrivateKey, bytes]:
    key = Ed25519PrivateKey.generate()
    public_pem = key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    return key, public_pem


def _artifact(tmp_path: Path, content: bytes = b"firmware-bytes") -> Path:
    path = tmp_path / "aurora_sensor_agent-1.1.0-py3-none-any.whl"
    path.write_bytes(content)
    return path


def _payload_for(artifact: Path, version: str = "1.1.0") -> dict[str, object]:
    return {
        "version": version,
        "artifact": artifact.name,
        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "size": artifact.stat().st_size,
        "released_at": "2026-09-28T00:00:00+00:00",
    }


def _sign(payload: dict[str, object], key: Ed25519PrivateKey) -> str:
    signature = key.sign(canonical_payload_bytes(payload))
    return json.dumps(
        {
            "payload": payload,
            "signature": base64.b64encode(signature).decode("ascii"),
            "algorithm": "ed25519",
        }
    )


# --- version helpers -------------------------------------------------------------------------


def test_parse_version_ignores_prerelease_suffix() -> None:
    assert parse_version("1.2.3-rc1") == (1, 2, 3)


def test_parse_version_rejects_garbage() -> None:
    with pytest.raises(OtaError):
        parse_version("not-a-version")


def test_is_newer() -> None:
    assert is_newer("1.2.0", "1.1.9") is True
    assert is_newer("1.1.0", "1.1.0") is False
    assert is_newer("1.0.0", "1.1.0") is False


# --- signature verification ------------------------------------------------------------------


def test_valid_manifest_verifies(tmp_path: Path) -> None:
    key, public_pem = _keypair()
    artifact = _artifact(tmp_path)
    manifest = _sign(_payload_for(artifact), key)

    payload = verify_manifest(manifest, public_pem)

    assert payload.version == "1.1.0"
    assert payload.artifact == artifact.name


def test_tampered_payload_fails(tmp_path: Path) -> None:
    key, public_pem = _keypair()
    artifact = _artifact(tmp_path)
    document = json.loads(_sign(_payload_for(artifact), key))
    document["payload"]["version"] = "9.9.9"  # change after signing

    with pytest.raises(OtaVerificationError, match="signature does not verify"):
        verify_manifest(json.dumps(document), public_pem)


def test_wrong_public_key_fails(tmp_path: Path) -> None:
    key, _ = _keypair()
    _, other_public = _keypair()
    artifact = _artifact(tmp_path)
    manifest = _sign(_payload_for(artifact), key)

    with pytest.raises(OtaVerificationError, match="signature does not verify"):
        verify_manifest(manifest, other_public)


def test_non_json_manifest_fails() -> None:
    _, public_pem = _keypair()
    with pytest.raises(OtaVerificationError, match="not valid JSON"):
        verify_manifest("{not json", public_pem)


def test_missing_signature_fails(tmp_path: Path) -> None:
    _, public_pem = _keypair()
    artifact = _artifact(tmp_path)
    document = {"payload": _payload_for(artifact)}
    with pytest.raises(OtaVerificationError, match="payload.*signature"):
        verify_manifest(json.dumps(document), public_pem)


def test_bad_base64_signature_fails(tmp_path: Path) -> None:
    _, public_pem = _keypair()
    artifact = _artifact(tmp_path)
    document = {"payload": _payload_for(artifact), "signature": "!!not base64!!"}
    with pytest.raises(OtaVerificationError, match="base64"):
        verify_manifest(json.dumps(document), public_pem)


def test_unsupported_algorithm_fails(tmp_path: Path) -> None:
    key, public_pem = _keypair()
    artifact = _artifact(tmp_path)
    document = json.loads(_sign(_payload_for(artifact), key))
    document["algorithm"] = "rsa"
    with pytest.raises(OtaVerificationError, match="algorithm"):
        verify_manifest(json.dumps(document), public_pem)


# --- artifact integrity ----------------------------------------------------------------------


def test_artifact_matches(tmp_path: Path) -> None:
    key, _ = _keypair()
    artifact = _artifact(tmp_path)
    payload = verify_manifest(_sign(_payload_for(artifact), key), _keypair_public(key))
    verify_artifact(artifact, payload)  # no raise


def _keypair_public(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)


def test_artifact_size_mismatch_fails(tmp_path: Path) -> None:
    key, public_pem = _keypair()
    artifact = _artifact(tmp_path)
    manifest = _sign(_payload_for(artifact), key)
    payload = verify_manifest(manifest, public_pem)
    artifact.write_bytes(b"longer-firmware-bytes")  # size changes after signing

    with pytest.raises(OtaVerificationError, match="size"):
        verify_artifact(artifact, payload)


def test_artifact_sha_mismatch_fails(tmp_path: Path) -> None:
    key, public_pem = _keypair()
    artifact = _artifact(tmp_path)
    manifest = _sign(_payload_for(artifact), key)
    payload = verify_manifest(manifest, public_pem)
    artifact.write_bytes(b"tampered-byte!")  # same length, different content

    with pytest.raises(OtaVerificationError, match="SHA-256"):
        verify_artifact(artifact, payload)


def test_missing_artifact_fails(tmp_path: Path) -> None:
    key, public_pem = _keypair()
    artifact = _artifact(tmp_path)
    payload = verify_manifest(_sign(_payload_for(artifact), key), public_pem)
    artifact.unlink()

    with pytest.raises(OtaVerificationError, match="not found"):
        verify_artifact(artifact, payload)


# --- prepare_update (the whole gate) ---------------------------------------------------------


def test_prepare_update_accepts_a_genuine_upgrade(tmp_path: Path) -> None:
    key, public_pem = _keypair()
    artifact = _artifact(tmp_path)
    manifest = _sign(_payload_for(artifact, version="1.2.0"), key)

    payload = prepare_update(manifest, public_pem, artifact, current_version="1.1.0")

    assert payload.version == "1.2.0"


def test_prepare_update_refuses_downgrade(tmp_path: Path) -> None:
    key, public_pem = _keypair()
    artifact = _artifact(tmp_path)
    manifest = _sign(_payload_for(artifact, version="1.0.0"), key)

    with pytest.raises(OtaVerificationError, match="not newer"):
        prepare_update(manifest, public_pem, artifact, current_version="1.1.0")


def test_prepare_update_refuses_tampered_artifact(tmp_path: Path) -> None:
    key, public_pem = _keypair()
    artifact = _artifact(tmp_path)
    manifest = _sign(_payload_for(artifact, version="1.2.0"), key)
    artifact.write_bytes(b"tampered-byte!")

    with pytest.raises(OtaVerificationError, match="SHA-256"):
        prepare_update(manifest, public_pem, artifact, current_version="1.1.0")
