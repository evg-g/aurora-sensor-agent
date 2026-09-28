#!/usr/bin/env python
"""Build (and optionally verify) a signed OTA update manifest for a release artifact.

The manifest is a small JSON document:

    {
      "payload": {"version", "artifact", "sha256", "size", "released_at", "min_agent_version"},
      "signature": "<base64 Ed25519 over the canonical payload>",
      "algorithm": "ed25519"
    }

The signature covers the canonical form of ``payload`` (sorted keys, no spaces) — exactly the bytes
the agent re-derives when it verifies (``aurora_sensor_agent.ota.canonical_payload_bytes``), so the
signer and the verifier always hash the same thing.

Usage:
    uv run python scripts/build_ota_manifest.py \
        --artifact dist/aurora_sensor_agent-1.1.0-py3-none-any.whl \
        --version 1.1.0 --private-key keys/ota_private.pem --out dist/manifest.json

    uv run python scripts/build_ota_manifest.py --verify \
        --artifact dist/aurora_sensor_agent-1.1.0-py3-none-any.whl \
        --manifest dist/manifest.json --public-key keys/ota_public.pem
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from aurora_sensor_agent.ota import (
    SIGNATURE_ALGORITHM,
    OtaVerificationError,
    canonical_payload_bytes,
    prepare_update,
    verify_artifact,
    verify_manifest,
)


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def build(
    artifact: Path,
    version: str,
    private_key_pem: bytes,
    *,
    released_at: str | None,
    min_agent_version: str | None,
) -> dict[str, object]:
    key = load_pem_private_key(private_key_pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise SystemExit("private key is not an Ed25519 key")

    payload: dict[str, object] = {
        "version": version,
        "artifact": artifact.name,
        "sha256": _sha256(artifact),
        "size": artifact.stat().st_size,
        "released_at": released_at or datetime.now(UTC).isoformat(),
    }
    if min_agent_version is not None:
        payload["min_agent_version"] = min_agent_version

    signature = key.sign(canonical_payload_bytes(payload))
    return {
        "payload": payload,
        "signature": base64.b64encode(signature).decode("ascii"),
        "algorithm": SIGNATURE_ALGORITHM,
    }


def _cmd_build(args: argparse.Namespace) -> int:
    manifest = build(
        args.artifact,
        args.version,
        args.private_key.read_bytes(),
        released_at=args.released_at,
        min_agent_version=args.min_agent_version,
    )
    text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if args.out is not None:
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote manifest -> {args.out}")
    else:
        sys.stdout.write(text)
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    manifest_json = args.manifest.read_text(encoding="utf-8")
    public_key_pem = args.public_key.read_bytes()
    try:
        if args.current_version is not None:
            payload = prepare_update(
                manifest_json, public_key_pem, args.artifact, args.current_version
            )
        else:
            payload = verify_manifest(manifest_json, public_key_pem)
            verify_artifact(args.artifact, payload)
    except OtaVerificationError as exc:
        print(f"OTA verification FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"OTA verification OK: version {payload.version}, artifact {payload.artifact}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or verify a signed OTA manifest.")
    parser.add_argument("--verify", action="store_true", help="Verify instead of build.")
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--version", help="Release version (build mode).")
    parser.add_argument("--private-key", type=Path, help="Ed25519 private key PEM (build mode).")
    parser.add_argument("--out", type=Path, help="Where to write the manifest (build mode).")
    parser.add_argument("--released-at", help="Override the released_at timestamp (build mode).")
    parser.add_argument("--min-agent-version", help="Minimum agent version required (build mode).")
    parser.add_argument("--manifest", type=Path, help="Manifest to verify (verify mode).")
    parser.add_argument("--public-key", type=Path, help="Ed25519 public key PEM (verify mode).")
    parser.add_argument("--current-version", help="Running version, to check upgrade direction.")
    args = parser.parse_args(argv)

    if args.verify:
        missing = [n for n in ("manifest", "public_key") if getattr(args, n) is None]
        if missing:
            parser.error("--verify requires --manifest and --public-key")
        return _cmd_verify(args)

    missing = [n for n in ("version", "private_key") if getattr(args, n) is None]
    if missing:
        parser.error("build mode requires --version and --private-key")
    return _cmd_build(args)


if __name__ == "__main__":
    raise SystemExit(main())
