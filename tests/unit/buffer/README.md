# tests/unit/buffer — the store-and-forward buffer

Tests for `src/aurora_sensor_agent/buffer/sqlite.py`, the local SQLite buffer that holds readings
until the server confirms them.

They use `:memory:` for the fast cases and a real file under `tmp_path` to prove readings survive a
close/reopen (a reboot). No network, no Docker.

What they prove:

- append → pending → acknowledge round-trips, oldest-first ordering, and `limit`.
- The bounded ring buffer: once capacity is reached, the **oldest** un-sent reading is evicted, so a
  device offline for a week cannot fill its disk.
- Row ids are monotonic and never reused (SQLite `AUTOINCREMENT`), which is what lets the server
  deduplicate `(device_id, sequence)` pairs.
- Buffered readings survive the store being closed and reopened.
