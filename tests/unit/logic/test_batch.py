"""Tests for batch splitting and the stable per-batch idempotency key."""

from __future__ import annotations

import json

import pytest

from aurora_sensor_agent.logic.batch import build_batches, split


def _rows(n: int) -> list[tuple[int, str]]:
    return [(i, json.dumps({"seq": i})) for i in range(1, n + 1)]


def test_split_chunks_preserve_order() -> None:
    assert split([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_split_rejects_zero_max() -> None:
    with pytest.raises(ValueError, match="max_count must be"):
        split([1, 2], 0)


def test_build_batches_respects_max_readings() -> None:
    batches = build_batches(_rows(5), device_id="dev-1", max_readings=2)
    assert [len(b.row_ids) for b in batches] == [2, 2, 1]
    assert batches[0].row_ids == [1, 2]


def test_build_batches_respects_max_bytes() -> None:
    rows = _rows(4)
    per_row = len(rows[0][1].encode())
    # A cap just under two rows forces one row per batch.
    batches = build_batches(rows, device_id="dev-1", max_readings=10, max_bytes=per_row + 1)
    assert [len(b.row_ids) for b in batches] == [1, 1, 1, 1]


def test_idempotency_key_is_stable_for_the_same_rows() -> None:
    rows = _rows(3)
    first = build_batches(rows, device_id="dev-1", max_readings=10)[0]
    second = build_batches(rows, device_id="dev-1", max_readings=10)[0]
    assert first.idempotency_key == second.idempotency_key


def test_idempotency_key_changes_with_content() -> None:
    a = build_batches(_rows(3), device_id="dev-1", max_readings=10)[0]
    b = build_batches(_rows(4), device_id="dev-1", max_readings=10)[0]
    assert a.idempotency_key != b.idempotency_key


def test_envelope_carries_sequence_and_device() -> None:
    batch = build_batches(_rows(2), device_id="fridge-A", max_readings=10)[0]
    envelope = json.loads(batch.payload)
    assert envelope["device_id"] == "fridge-A"
    assert [r["sequence"] for r in envelope["readings"]] == [1, 2]
    assert envelope["idempotency_key"] == batch.idempotency_key
