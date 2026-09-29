"""Over-the-air update verification: the device must prove an update is genuine before applying it.

A field device that installs whatever bytes arrive over the network is a fleet-wide remote-code-
execution waiting to happen. So the release pipeline ships a small **signed manifest** alongside the
artifact (a wheel, or a ``.deb``), and the agent refuses to apply anything that does not pass three
checks, in order:

1. **Signature** — the manifest's ``payload`` is signed with the release private key (Ed25519). The
   agent holds only the matching *public* key, pinned into the image, and rejects the manifest if
   the signature does not verify. This is what stops an attacker (or a corrupted mirror) from
   serving a malicious update: they cannot forge the signature without the private key.
2. **Integrity** — the artifact's SHA-256 and byte size must match the signed manifest, so a
   truncated or tampered download is caught even though the manifest itself is valid.
3. **Direction** — the manifest version must be newer than what is running, so a signed *old* build
   cannot be replayed to roll a device back onto a known-vulnerable version.

Only the verification lives here — the security-critical part, and the one worth testing hard. The
actual swap — replacing the venv/package and restarting the systemd service — is a packaging concern
handled by the ``.deb`` post-install script (see ``docs/PACKAGING.md``); this module hands it a
manifest it has already proven trustworthy.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from pydantic import BaseModel, Field

SIGNATURE_ALGORITHM = "ed25519"


class OtaError(Exception):
    """Base class for OTA problems."""


class OtaVerificationError(OtaError):
    """The manifest signature, the artifact integrity, or the version direction check failed."""


class OtaManifestPayload(BaseModel):
    """The signed part of an OTA manifest — everything the signature covers."""

    version: str = Field(min_length=1)
    artifact: str = Field(min_length=1)
    sha256: str = Field(min_length=64, max_length=64)
    size: int = Field(ge=0)
    released_at: str = Field(min_length=1)
    min_agent_version: str | None = None


def canonical_payload_bytes(payload: dict[str, object]) -> bytes:
    """Serialise a payload deterministically so signer and verifier hash identical bytes."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def parse_version(version: str) -> tuple[int, ...]:
    """Parse ``"1.2.0"`` into ``(1, 2, 0)`` for comparison. Ignores any ``-pre`` suffix.

    Raises ``OtaError`` on a version that is not dot-separated integers, so a malformed version in a
    manifest is rejected loudly rather than silently sorting wrong.
    """
    core = version.split("-", 1)[0].split("+", 1)[0]
    try:
        return tuple(int(part) for part in core.split("."))
    except ValueError as exc:
        raise OtaError(f"unparseable version {version!r}") from exc


def is_newer(candidate: str, current: str) -> bool:
    """True if ``candidate`` is a strictly newer version than ``current``."""
    return parse_version(candidate) > parse_version(current)


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_manifest(manifest_json: str | bytes, public_key_pem: bytes) -> OtaManifestPayload:
    """Verify the manifest signature and return the trusted payload. Raises on any failure."""
    try:
        document = json.loads(manifest_json)
    except json.JSONDecodeError as exc:
        raise OtaVerificationError(f"manifest is not valid JSON: {exc}") from exc

    if not isinstance(document, dict) or "payload" not in document or "signature" not in document:
        raise OtaVerificationError("manifest must have 'payload' and 'signature'")
    if document.get("algorithm", SIGNATURE_ALGORITHM) != SIGNATURE_ALGORITHM:
        raise OtaVerificationError(f"unsupported signature algorithm {document.get('algorithm')!r}")

    public_key = load_pem_public_key(public_key_pem)
    if not isinstance(public_key, Ed25519PublicKey):
        raise OtaVerificationError("public key is not an Ed25519 key")

    try:
        signature = base64.b64decode(document["signature"], validate=True)
    except (ValueError, TypeError) as exc:
        raise OtaVerificationError(f"signature is not valid base64: {exc}") from exc

    signed_bytes = canonical_payload_bytes(document["payload"])
    try:
        public_key.verify(signature, signed_bytes)
    except InvalidSignature as exc:
        raise OtaVerificationError("manifest signature does not verify") from exc

    return OtaManifestPayload.model_validate(document["payload"])


def verify_artifact(artifact_path: Path, payload: OtaManifestPayload) -> None:
    """Check the artifact matches the signed size and SHA-256. Raises on any mismatch."""
    if not artifact_path.is_file():
        raise OtaVerificationError(f"artifact not found: {artifact_path}")
    actual_size = artifact_path.stat().st_size
    if actual_size != payload.size:
        raise OtaVerificationError(f"artifact size {actual_size} != signed size {payload.size}")
    actual_sha = _sha256_file(artifact_path)
    if actual_sha.lower() != payload.sha256.lower():
        raise OtaVerificationError("artifact SHA-256 does not match the signed manifest")


def prepare_update(
    manifest_json: str | bytes,
    public_key_pem: bytes,
    artifact_path: Path,
    current_version: str,
) -> OtaManifestPayload:
    """Run all three checks and return the verified manifest, ready to apply. Raises on any failure.

    This is the single entry point the update flow calls: if it returns, the artifact at
    ``artifact_path`` is genuine, intact, and a real upgrade over ``current_version``.
    """
    payload = verify_manifest(manifest_json, public_key_pem)
    verify_artifact(artifact_path, payload)
    if not is_newer(payload.version, current_version):
        raise OtaVerificationError(
            f"refusing to apply {payload.version}: not newer than running {current_version}"
        )
    return payload


__all__ = [
    "SIGNATURE_ALGORITHM",
    "OtaError",
    "OtaManifestPayload",
    "OtaVerificationError",
    "canonical_payload_bytes",
    "is_newer",
    "parse_version",
    "prepare_update",
    "verify_artifact",
    "verify_manifest",
]
