#!/usr/bin/env python
"""Telemetry-contract drift gate — the owner side (spec §8 rule 4).

This repo (``aurora-sensor-agent``) **owns** the telemetry contract: the JSON Schema for the batch
envelope and the AsyncAPI 3 document, both under ``contracts/``. The API repo vendors a copy and
validates every inbound message against it. So drift has to be gated from *both* sides — the API's
``check_telemetry_contract.py`` is this check in reverse.

Two checks:

1. **In-repo guard (always):** each contract file's SHA-256 must match
   ``contracts/CHECKSUMS.sha256``. That file is only updated deliberately, with ``--record``, so an
   accidental edit to the schema (or one that forgot to bump the version) fails the gate instead of
   silently shipping.
2. **Cross-repo drift (when the API repo is present):** the contract files must be byte-identical to
   the API's vendored copy in ``src/appointments_api/contracts/telemetry/``. If the sibling repo is
   not checked out (a fork's CI), the check skips cleanly and stays green — the same "skip without
   inputs" pattern as the deploy jobs.

Point at the API repo with ``AURORA_API_REPO`` (defaults to ``../appointments-api``).

Usage:
    uv run python scripts/check_contract.py            # run the gate
    uv run python scripts/check_contract.py --record   # rewrite CHECKSUMS.sha256 after a change
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

CONTRACTS = Path("contracts")
FILES = ("telemetry.schema.json", "telemetry.asyncapi.yaml")
CHECKSUMS = CONTRACTS / "CHECKSUMS.sha256"
VENDORED_SUBPATH = Path("src/appointments_api/contracts/telemetry")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_checksums(path: Path) -> dict[str, str]:
    recorded: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, name = line.split()
        recorded[name] = digest
    return recorded


def record() -> int:
    lines = [f"{_sha256(CONTRACTS / name)}  {name}\n" for name in FILES]
    CHECKSUMS.write_text("".join(lines), encoding="utf-8")
    print(f"recorded checksums for {', '.join(FILES)} in {CHECKSUMS}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if "--record" in args:
        return record()

    recorded = _read_checksums(CHECKSUMS)
    for name in FILES:
        actual = _sha256(CONTRACTS / name)
        if actual != recorded.get(name):
            print(
                f"contract {name} does not match {CHECKSUMS} (edited without --record?). "
                f"If the change is intentional, bump the schema version and re-record.",
                file=sys.stderr,
            )
            return 1
    print("in-repo guard: contract files match their recorded checksums.")

    api_repo = Path(os.environ.get("AURORA_API_REPO", "../appointments-api"))
    vendored = api_repo / VENDORED_SUBPATH
    if not vendored.is_dir():
        print(f"API repo not present at {api_repo} — skipping cross-repo drift check.")
        return 0

    drifted = [
        name for name in FILES if (CONTRACTS / name).read_bytes() != (vendored / name).read_bytes()
    ]
    if drifted:
        print(
            "telemetry contract drift vs the API's vendored copy: "
            + ", ".join(drifted)
            + ".\nRe-vendor the API from this repo's contracts/.",
            file=sys.stderr,
        )
        return 1
    print("cross-repo check: the API's vendored copy matches this repo's contract.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
