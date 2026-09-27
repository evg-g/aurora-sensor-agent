"""Split buffered readings into publish batches, each with a stable idempotency key.

Draining the buffer one reading at a time would be wasteful; sending everything in one giant
message risks exceeding the broker's payload limit. So readings are grouped into batches bounded by
a maximum count (and optionally a maximum byte size).

Each batch carries a **device-generated idempotency key** derived deterministically from the rows it
contains. If the uplink fails halfway and the same rows are retried, the key is identical, so the
server can drop the duplicate batch instead of storing the readings twice — "at least once" delivery
made safe. The buffer row id doubles as the reading's ``sequence`` (SQLite ``AUTOINCREMENT`` never
reuses an id), which is the ``(device_id, sequence)`` pair the server deduplicates on.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypeVar

SCHEMA_VERSION = 1

T = TypeVar("T")


def split(items: Sequence[T], max_count: int) -> list[list[T]]:
    """Split ``items`` into chunks of at most ``max_count`` (order preserved)."""
    if max_count < 1:
        raise ValueError(f"max_count must be >= 1, got {max_count}")
    return [list(items[i : i + max_count]) for i in range(0, len(items), max_count)]


@dataclass(frozen=True, slots=True)
class Batch:
    """A ready-to-publish group of readings.

    ``row_ids`` are the buffer ids to acknowledge once the server confirms delivery. ``payload`` is
    the serialised envelope. ``idempotency_key`` is stable across retries of the same rows.
    """

    idempotency_key: str
    row_ids: list[int]
    payload: bytes


def _idempotency_key(rows: Sequence[tuple[int, str]]) -> str:
    """A stable key for a set of rows: SHA-256 over ``id:payload`` lines, in id order."""
    hasher = hashlib.sha256()
    for row_id, payload in sorted(rows):
        hasher.update(f"{row_id}:{payload}".encode())
        hasher.update(b"\n")
    return hasher.hexdigest()


def build_batches(
    pending: Sequence[tuple[int, str]],
    *,
    device_id: str,
    max_readings: int,
    max_bytes: int | None = None,
) -> list[Batch]:
    """Group ``pending`` ``(row_id, reading_json)`` rows into publishable batches.

    Rows are chunked by ``max_readings`` first; if ``max_bytes`` is set, a chunk that would exceed
    it is split further so no single payload is oversized. A reading larger than ``max_bytes`` is
    sent on its own (better an oversized lone message than a dropped reading).
    """
    batches: list[Batch] = []
    for chunk in split(pending, max_readings):
        for sized_chunk in _limit_bytes(chunk, max_bytes):
            batches.append(_make_batch(sized_chunk, device_id))
    return batches


def _limit_bytes(
    chunk: Sequence[tuple[int, str]], max_bytes: int | None
) -> list[list[tuple[int, str]]]:
    if max_bytes is None:
        return [list(chunk)]
    groups: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    size = 0
    for row in chunk:
        row_bytes = len(row[1].encode())
        if current and size + row_bytes > max_bytes:
            groups.append(current)
            current, size = [], 0
        current.append(row)
        size += row_bytes
    if current:
        groups.append(current)
    return groups


def _make_batch(rows: Sequence[tuple[int, str]], device_id: str) -> Batch:
    key = _idempotency_key(rows)
    envelope = {
        "v": SCHEMA_VERSION,
        "device_id": device_id,
        "idempotency_key": key,
        "readings": [
            {"sequence": row_id, "reading": json.loads(payload)} for row_id, payload in rows
        ],
    }
    payload = json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode()
    return Batch(
        idempotency_key=key,
        row_ids=[row_id for row_id, _ in rows],
        payload=payload,
    )


__all__ = ["SCHEMA_VERSION", "Batch", "build_batches", "split"]
