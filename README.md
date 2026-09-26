# aurora-sensor-agent

The device-side agent for **Aurora Clinic** cold-chain monitoring. A Python program that
runs on a small board (Raspberry Pi Zero 2 W) next to a clinic's medical fridge, reads a
temperature/humidity sensor, detects cold-chain breaches, buffers readings when offline,
and reports them to the backend.

One of three repos in the system — see the top-level `README.md`.

## Why this exists

To practice **Python on the device side and testing hardware-facing code without owning
hardware**. Every hardware touchpoint (I²C bus, serial port, GPIO, clock, network) sits
behind a `typing.Protocol`, so the same logic runs against real hardware, a physics-flavoured
simulator, or recorded traces — and the test suite runs on a plain laptop with no hardware,
no network, and no Docker.

## Status

Milestone 1 (scaffolding). Currently ships the SHT4x **CRC-8** primitive and a CLI stub.
The sensor drivers, excursion state machine, buffer, and MQTT transport arrive in later
milestones (see the top-level `PLAN.md`).

## Quick start

```bash
# WSL (Ubuntu-24.04)
make setup
make test
aurora-agent --version   # after: uv run aurora-agent --version
```

## Layout

```
src/aurora_sensor_agent/
  protocol/      # wire-level: CRC, register maps, framing
  cli.py         # entry point
tests/           # unit / driver_contract / faults / sil / soak / hil
```

## License

MIT — see `LICENSE`.
