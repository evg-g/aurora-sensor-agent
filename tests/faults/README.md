# tests/faults — the fault-injection catalogue

The device must behave correctly when things go wrong. The fault catalogue splits in two:

- **Chip/bus faults** (bad CRC, NACK, timeout, short read, power loss, stuck) are injected at the
  I²C seam and tested in `tests/unit/sim/test_faults.py`.
- **Higher-layer faults** (NaN in the pipeline, disk full, clock jump) are injected at the
  pipeline/buffer/clock seams and tested here (`test_pipeline_faults.py`).

The property every fault must satisfy: **it never loses already-buffered data and never produces a
duplicate on the server.** The tests prove:

- a NaN reading is rejected and never enters the buffer;
- a full disk is flagged, does not crash the agent, and does not lose readings already buffered
  (they still drain when the write fails);
- a transient write error recovers on the next write;
- a backward clock step produces no spurious excursion;
- a retried batch reuses its idempotency key, so the server can drop the duplicate.

A guard test (`test_every_pipeline_fault_has_coverage`) fails if a new fault is added to the
catalogue without a matching test.
