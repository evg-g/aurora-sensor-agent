# 1. Put every hardware touchpoint behind a Protocol

- Status: accepted
- Date: 2026-09-26

## Context

This agent talks to real hardware (I²C sensor, serial probe, GPIO, a network transport). If
the code imported and called those libraries directly, it could only be tested on a real
Raspberry Pi with a real sensor wired up. That makes tests slow, flaky, and impossible to run
in CI or on a laptop.

## Decision

Every hardware and I/O touchpoint is defined as a `typing.Protocol` (`I2CBus`, `SerialPort`,
`GpioPin`, `Clock`, `Transport`, `BufferStore`). Concrete implementations live behind a
factory: `real/` (lazy hardware imports), `sim/` (deterministic simulator), `replay/`
(recorded traces). A single abstract driver-contract test suite runs against all three.

## Consequences

- The whole logic layer is testable on any laptop with no hardware, network, or Docker.
- Swapping real ↔ simulator ↔ replay is a one-line factory change.
- `real/` must keep its hardware imports lazy so the package imports cleanly everywhere.
- There is a small cost: one extra indirection (the protocol) for every device interaction.
