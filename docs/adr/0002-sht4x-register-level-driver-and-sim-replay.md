# 2. Model the SHT4x at the register level, with a deterministic sim and byte-for-byte replay

- Status: accepted
- Date: 2026-09-27

## Context

The agent's job starts with one thing: read a temperature from a real chip over I²C and trust the
number. We could have hidden that behind a library call that returns a float. But the whole point of
this repo is to *practise testing hardware code*, and a float-returning shim teaches nothing and
hides the failures that actually happen on a wire: a flipped bit, a chip read before it has finished
converting, a sensor that wedges on one value.

ADR 0001 already decided that every hardware touchpoint sits behind a `Protocol`. This ADR decides
*how* the SHT4x specifically is built and tested.

## Decision

**Drive the chip at the register level.** `Sht4xDriver` speaks the real wire protocol — command byte
(`0xFD` for a high-precision measurement), wait the conversion time, read six bytes as two 16-bit
words each followed by a CRC-8, verify both checksums, then convert raw counts to °C and %RH with the
datasheet formulas. The driver talks only to an `I2CBus` seam and an injected `Clock`; it never
imports a hardware library.

**Three buses satisfy that one seam:**

| Bus | What it is | Runs where |
|---|---|---|
| `sim` | A register-level chip simulator: real command bytes, real conversion delay, real CRCs, values from a seeded fridge `ThermalModel`. Injects faults on demand. | Everywhere |
| `replay` | Returns recorded 6-byte frames from a `.jsonl` trace, in order. | Everywhere |
| `real` | `smbus2` on a Raspberry Pi. Imports are lazy, so the module loads with no hardware. | On a device |

**One contract suite runs against all three** (`tests/driver_contract/`). If the simulator and a
recorded trace pass the same behavioural tests the real bus is held to, swapping one for another is
safe — which is what lets almost the entire agent be built and tested on a laptop.

**Determinism is enforced at the source.** The simulator is pure in time: `sample(t)` depends only on
`t` and the seed, never on call order, and its randomness is mixed from integers (never string
hashing), so it is identical across processes and `PYTHONHASHSEED` values. That is what makes a
captured trace reproducible byte-for-byte.

## Consequences

- The wire-level failure modes are first-class and testable: `test_measure_rejects_corrupted_crc`,
  `test_reading_before_conversion_time_fails`, the fault catalogue in `tests/unit/sim/test_faults.py`.
- The simulated chip enforces the conversion delay, so a driver that reads too early *fails a test*
  instead of returning stale bytes — the timing contract is verified, not assumed.
- A regression can be frozen forever: record the exact frames that triggered a bug into a trace and
  replay them.
- Cost: the sim carries a small physics model and a fault state machine. That is deliberate — those
  are the parts that make the excursion logic (milestone 9) worth testing.
- The full fault catalogue includes failures above the bus (NaN in the pipeline, disk full in the
  buffer, a clock jump). Those are not I²C faults; they are injected at the buffer/clock seams in
  milestone 9. This ADR covers the chip/bus faults only.
