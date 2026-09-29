#!/usr/bin/env python
"""Generate an Ed25519 keypair for signing OTA manifests.

The **private** key signs releases and never leaves the release pipeline (in CI it lives in a
secret, not on disk). The **public** key is pinned into the agent image so a device can verify an
update. This script is for local demos and for bootstrapping the CI secret; it writes both keys to
the ``keys/`` directory, which is gitignored.

Usage:
    uv run python scripts/gen_ota_key.py
    uv run python scripts/gen_ota_key.py --private-out keys/priv.pem --public-out keys/pub.pem
"""

from __future__ import annotations

import argparse
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)


def generate(private_out: Path, public_out: Path) -> None:
    key = Ed25519PrivateKey.generate()
    private_pem = key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    public_pem = key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)

    private_out.parent.mkdir(parents=True, exist_ok=True)
    public_out.parent.mkdir(parents=True, exist_ok=True)
    private_out.write_bytes(private_pem)
    private_out.chmod(0o600)
    public_out.write_bytes(public_pem)
    print(f"wrote private key -> {private_out} (keep secret)")
    print(f"wrote public key  -> {public_out} (pin into the agent)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate an Ed25519 OTA signing keypair.")
    parser.add_argument("--private-out", type=Path, default=Path("keys/ota_private.pem"))
    parser.add_argument("--public-out", type=Path, default=Path("keys/ota_public.pem"))
    args = parser.parse_args(argv)
    generate(args.private_out, args.public_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
