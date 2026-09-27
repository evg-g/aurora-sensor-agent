# tests/unit/serial — the legacy UART probe

Tests for `src/aurora_sensor_agent/drivers/legacy_probe.py`, the second temperature probe on a plain
serial line with an ASCII, checksum-framed protocol.

Two layers:

- **Frame parser (pure):** split frames across reads, leading garbage, a bad checksum, a non-hex
  checksum, and a malformed terminator — all with no I/O. The parser resynchronises past junk and
  counts checksum failures.
- **I/O over real serial doubles:** `pyserial`'s `loop://` (an in-memory loopback) and a `pty` pair
  (a real kernel pseudo-terminal, POSIX only). These run the actual `pyserial` read path with no
  hardware, covering a happy read, a timeout, and skipping a corrupt frame.

The `pty` test is skipped on Windows (`pty` is POSIX-only); everything else runs everywhere.
