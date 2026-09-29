# 4. A bounded SQLite store-and-forward buffer, drained in idempotent batches

- Status: accepted
- Date: 2026-09-27

## Context

The network is not always there. A clinic's link drops, the broker restarts, the device reboots. A
reading taken during any of that must not be lost — a gap in the cold-chain record is exactly the
thing an auditor asks about. But the device is a Raspberry Pi with a small SD card, so "just keep
everything" is not an option either: a device offline for a week must not fill its disk and brick
itself.

Once the link returns, the backlog has to be sent. Sending it one reading at a time is wasteful;
sending it all in one message risks exceeding the broker's payload limit. And because delivery is
"at least once" (the device retries after a failure), the same readings can arrive twice.

## Decision

**Write before you send.** Every reading is appended to a local SQLite buffer *before* any publish
attempt, and only deleted once the server confirms it. On restart the un-sent readings are still on
disk, so a power cut loses nothing.

**Bound the buffer with a ring policy.** The buffer has a `capacity`; once full, the *oldest* un-sent
reading is dropped to make room for the newest. Recent readings matter more than stale ones, and a
bounded buffer is what the soak test proves never grows without limit. The count of evicted rows is a
health signal.

**The row id is the sequence.** The table uses `INTEGER PRIMARY KEY AUTOINCREMENT`, so ids are
monotonic and never reused even after rows are deleted. That id is the reading's `sequence`, and
`(device_id, sequence)` is what the server deduplicates on.

**Drain in batches with a stable idempotency key.** Buffered rows are grouped into batches bounded by
a maximum count (and optionally a maximum byte size). Each batch carries a device-generated
idempotency key derived deterministically (SHA-256) from the rows it contains. If a publish fails
halfway and the same rows are retried, the key is identical, so the server drops the duplicate batch
instead of storing the readings twice.

**Fail soft on a full disk.** If a buffer write fails (disk full), the agent flags it and drops that
one reading, but still tries to drain — uploading what is already buffered is what frees the space
back up. It never crashes, and it never loses what was already safely written.

## Consequences

- Readings survive outages, reboots, and power cuts, up to the buffer capacity.
- The server can be given the same batch twice and end up with one copy, so "at least once" delivery
  is safe end to end. The actual MQTT/HTTP transports land in milestones 10-11; milestone 9 ships the
  buffer, the batching, the backoff, and an in-memory transport so the whole loop is testable now.
- Cost: at capacity, the oldest un-sent readings are lost on purpose. That is the deliberate
  trade-off; the alternative (an unbounded buffer) trades a data gap for a bricked device, which is
  worse. The eviction count makes the loss visible in the health beacon.
