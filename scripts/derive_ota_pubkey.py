#!/usr/bin/env python
"""Write the public key for an existing Ed25519 private key PEM.

Used by the CI package job when the release private key comes from a secret (so only the private key
is stored); the agent needs the matching public key to verify.

Usage:
    uv run python scripts/derive_ota_pubkey.py keys/ota_private.pem keys/ota_public.pem
"""

from __future__ import annotations

import sys
from pathlib import Path

from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_pem_private_key,
)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("usage: derive_ota_pubkey.py <private.pem> <public.pem>", file=sys.stderr)
        return 2
    private_path, public_path = Path(args[0]), Path(args[1])
    key = load_pem_private_key(private_path.read_bytes(), password=None)
    public_pem = key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    public_path.write_bytes(public_pem)
    print(f"wrote {public_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
