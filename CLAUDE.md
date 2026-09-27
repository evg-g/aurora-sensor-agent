# CLAUDE.md — aurora-sensor-agent conventions

Read this before changing anything in this repo.

## What this repo is

The IoT cold-chain sensor agent. Its whole point is **substitutability**: hardware is behind
protocols so the code is testable without hardware.

## Architecture rules

- Every hardware touchpoint is a `typing.Protocol`: `I2CBus`, `SerialPort`, `GpioPin`,
  `Clock`, `Transport`, `BufferStore`.
- Three implementations of the sensor stack, all satisfying the same driver contract test:
  `real/` (lazy `smbus2`/`pyserial`/`gpiozero` imports, must import cleanly with no hardware),
  `sim/` (seeded physics simulator with injectable faults), `replay/` (recorded traces).
- Pure logic (excursion state machine, filters, backoff) has zero I/O and takes an injected
  `Clock`.

## Non-negotiables

- No placeholders. Everything runnable.
- `mypy --strict` and `ruff` clean.
- Determinism: no real sleep, no real clock, seeded RNG. Tests run with no hardware, no
  network, no Docker (except the SIL tier).
- The `hil` tier is marked `@pytest.mark.hil` and deselected by default.

## Commands

```bash
make setup / make test / make lint / make ci-local
make sim     # run the SHT4x driver against the simulator (prints readings)
make run     # run the whole agent loop against the simulator (prints the health beacon)
make soak    # compressed seven-day soak test (fake clock, tracemalloc)
make fleet   # N virtual devices (milestone 11)
```
