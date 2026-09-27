"""Tests for the SQLite store-and-forward buffer.

These use ``:memory:`` for the in-process cases and a real file under ``tmp_path`` to prove readings
survive a close/reopen (a reboot). No network, no Docker.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aurora_sensor_agent.buffer.sqlite import SqliteBufferStore


def test_append_pending_acknowledge_roundtrip() -> None:
    with SqliteBufferStore(":memory:", capacity=100) as buffer:
        id1 = buffer.append('{"n":1}')
        id2 = buffer.append('{"n":2}')
        assert buffer.depth() == 2
        assert buffer.pending(10) == [(id1, '{"n":1}'), (id2, '{"n":2}')]

        buffer.acknowledge([id1])
        assert buffer.depth() == 1
        assert buffer.pending(10) == [(id2, '{"n":2}')]


def test_pending_returns_oldest_first_and_limits() -> None:
    with SqliteBufferStore(":memory:", capacity=100) as buffer:
        ids = [buffer.append(f'{{"n":{i}}}') for i in range(5)]
        pending = buffer.pending(3)
        assert [row_id for row_id, _ in pending] == ids[:3]


def test_capacity_evicts_oldest() -> None:
    with SqliteBufferStore(":memory:", capacity=3) as buffer:
        for i in range(5):
            buffer.append(f'{{"n":{i}}}')
        assert buffer.depth() == 3
        # The two oldest were dropped; the three newest remain, in order.
        payloads = [payload for _, payload in buffer.pending(10)]
        assert payloads == ['{"n":2}', '{"n":3}', '{"n":4}']
        assert buffer.evicted_total == 2


def test_row_ids_are_monotonic_and_never_reused() -> None:
    with SqliteBufferStore(":memory:", capacity=100) as buffer:
        id1 = buffer.append("a")
        buffer.acknowledge([id1])
        id2 = buffer.append("b")
        # AUTOINCREMENT: the id is not reused even though the first row was deleted.
        assert id2 > id1


def test_survives_close_and_reopen(tmp_path: Path) -> None:
    db = str(tmp_path / "buffer.sqlite")
    store = SqliteBufferStore(db, capacity=100)
    row_id = store.append('{"kept":true}')
    store.close()

    reopened = SqliteBufferStore(db, capacity=100)
    try:
        assert reopened.depth() == 1
        assert reopened.pending(10) == [(row_id, '{"kept":true}')]
    finally:
        reopened.close()


def test_acknowledge_empty_is_a_noop() -> None:
    with SqliteBufferStore(":memory:", capacity=10) as buffer:
        buffer.append("x")
        buffer.acknowledge([])
        assert buffer.depth() == 1


def test_zero_capacity_is_rejected() -> None:
    with pytest.raises(ValueError, match="capacity must be"):
        SqliteBufferStore(":memory:", capacity=0)
