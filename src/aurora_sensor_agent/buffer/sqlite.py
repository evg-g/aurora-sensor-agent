"""A SQLite store-and-forward buffer with a bounded, ring-buffer eviction policy.

Why store-and-forward: the network is not always there. A clinic's link drops, the broker restarts,
the device reboots. Readings must survive all of that, so every reading is written to a local SQLite
file *before* any attempt to send it, and only deleted once the server confirms it. On restart the
un-sent readings are still on disk, so nothing is lost to a power cut.

Why bounded: a device offline for a week must not fill its SD card and brick itself. The buffer has
a ``capacity``; once full, the **oldest** un-sent reading is dropped to make room for the newest.
That is a deliberate policy choice (ADR 0004): recent readings matter more than stale ones, and a
bounded buffer is what the soak test proves never grows without limit.

The row id is the reading's ``sequence``. ``INTEGER PRIMARY KEY AUTOINCREMENT`` guarantees ids are
monotonic and never reused, even after rows are deleted — exactly the property the server needs to
deduplicate ``(device_id, sequence)`` pairs.
"""

from __future__ import annotations

import sqlite3
from types import TracebackType


class SqliteBufferStore:
    """A ``BufferStore`` backed by a single SQLite table.

    ``path`` is a filename, or ``":memory:"`` for a throwaway in-process buffer (tests).
    ``capacity`` is the maximum number of un-acknowledged rows kept before the oldest are evicted.
    """

    def __init__(self, path: str, capacity: int) -> None:
        if capacity < 1:
            raise ValueError(f"capacity must be >= 1, got {capacity}")
        self._capacity = capacity
        # isolation_level=None → autocommit; we manage durability explicitly and keep it simple.
        self._conn = sqlite3.connect(path, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS buffered_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload TEXT NOT NULL
            )
            """
        )
        self._evicted = 0

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def evicted_total(self) -> int:
        """How many rows have ever been dropped by the eviction policy (a health signal)."""
        return self._evicted

    def append(self, reading_json: str) -> int:
        """Persist one serialised reading and return its row id, evicting the oldest if full."""
        cursor = self._conn.execute(
            "INSERT INTO buffered_readings (payload) VALUES (?)", (reading_json,)
        )
        row_id = cursor.lastrowid
        assert row_id is not None
        self._evict_over_capacity()
        return row_id

    def pending(self, limit: int) -> list[tuple[int, str]]:
        """Return up to ``limit`` oldest un-acknowledged ``(row_id, payload)`` rows."""
        if limit < 1:
            raise ValueError(f"limit must be >= 1, got {limit}")
        rows = self._conn.execute(
            "SELECT id, payload FROM buffered_readings ORDER BY id ASC LIMIT ?", (limit,)
        ).fetchall()
        return [(int(row_id), str(payload)) for row_id, payload in rows]

    def acknowledge(self, row_ids: list[int]) -> None:
        """Delete rows the server has confirmed."""
        if not row_ids:
            return
        # Placeholders come only from the id count; the ids themselves are bound parameters.
        placeholders = ",".join("?" for _ in row_ids)
        self._conn.execute(
            f"DELETE FROM buffered_readings WHERE id IN ({placeholders})",
            row_ids,
        )

    def depth(self) -> int:
        """Number of un-acknowledged rows currently buffered."""
        (count,) = self._conn.execute("SELECT COUNT(*) FROM buffered_readings").fetchone()
        return int(count)

    def close(self) -> None:
        self._conn.close()

    def _evict_over_capacity(self) -> None:
        overflow = self.depth() - self._capacity
        if overflow <= 0:
            return
        # Drop the oldest ``overflow`` rows (smallest ids).
        self._conn.execute(
            """
            DELETE FROM buffered_readings
            WHERE id IN (SELECT id FROM buffered_readings ORDER BY id ASC LIMIT ?)
            """,
            (overflow,),
        )
        self._evicted += overflow

    def __enter__(self) -> SqliteBufferStore:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


__all__ = ["SqliteBufferStore"]
