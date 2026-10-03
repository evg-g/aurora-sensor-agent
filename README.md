# aurora-sensor-agent

[![ci](https://github.com/evg-g/aurora-sensor-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/evg-g/aurora-sensor-agent/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Part of **[Aurora Clinic](https://github.com/evg-g/aurora)** — three repos, one product.

The device-side agent for **Aurora Clinic** cold-chain monitoring. A Python program that
runs on a small board (Raspberry Pi Zero 2 W) next to a clinic's medical fridge, reads a
temperature/humidity sensor, detects cold-chain breaches, buffers readings when offline,
and reports them to the backend.

One of three repos in the system — see the [top-level `README.md`](https://github.com/evg-g/aurora).

## Why this exists

To show **Python on the device side and how to test hardware-facing code without owning
hardware**. Every hardware touchpoint (I²C bus, serial port, GPIO, clock, network) sits
behind a `typing.Protocol`, so the same logic runs against real hardware, a physics-flavoured
simulator, or recorded traces — and the test suite runs on a plain laptop with no hardware,
no network, and no Docker.

## Status

Milestones 1–11 complete. The repo ships: the SHT4x register-level driver with CRC-8;
real/sim/replay I²C buses and a driver-contract suite; the excursion state machine, median
filter, backoff, and SQLite store-and-forward buffer; the serial and GPIO tiers; the full
fault catalogue and a compressed seven-day soak; **real MQTT (QoS 1) and HTTP-fallback
transports**; a **fleet simulator** and a **staged OTA rollout** with auto-halt; a **signed
OTA manifest** the agent verifies before applying; **software-in-the-loop** tests against a
real broker + the API in Docker; and packaging as a **.deb** and a gateway image. See the
[build plan](https://github.com/evg-g/aurora/blob/main/docs/process/PLAN.md).

## Quick start

```bash
# WSL (Ubuntu-24.04)
make setup           # create the venv and install deps
make ci-local        # lint + mypy --strict + contract gate + tests (no hardware/Docker)
make sim             # run the driver against the simulated sensor
make run             # run the whole agent loop against the simulator
make fleet           # run the virtual device fleet from fleet.yaml
make rollout         # staged OTA rollout (BAD_BUILD=1 to see the auto-halt)
make ota-demo        # generate a key, sign an artifact, verify the manifest
make sil             # software-in-the-loop (needs Docker + the API image)
make deb             # build the .deb (needs dpkg-deb)
```

## Layout

```
src/aurora_sensor_agent/
  protocol/      # wire-level: CRC, register maps, framing
  drivers/       # SHT4x + legacy serial probe drivers (talk to seams only)
  real/ sim/ replay/   # the three I²C/serial/GPIO implementations behind the seams
  logic/         # excursion machine, filter, backoff, batching, indicator (pure)
  buffer/        # SQLite store-and-forward
  transport/     # in-memory, MQTT (primary), HTTP (fallback), fallback wrapper
  fleet/         # fleet.yaml schema, fleet simulator, staged rollout
  ota.py         # verify a signed OTA manifest before applying
  cli.py         # entry point: sim / run / fleet / rollout
contracts/       # the telemetry contract this repo owns (schema + AsyncAPI)
packaging/       # systemd unit + Debian control/scripts
tests/           # unit / driver_contract / faults / contract / sil / soak / hil
```

## Docs

| Doc | What it covers |
|---|---|
| [`docs/HARDWARE_TESTING.md`](docs/HARDWARE_TESTING.md) | How a device agent is tested with no hardware: the protocol seams, the simulator, trace replay, fault injection, the compressed soak, and the SIL and HIL tiers. |
| [`docs/EXERCISES.md`](docs/EXERCISES.md) | Break-it-on-purpose exercises: make the change, predict which gate fails, run it, confirm. |
| [`docs/CI_CD.md`](docs/CI_CD.md) | The pipeline: lint, typecheck, tests, contract gate, SIL, packaging, and the security job. |
| [`docs/OTA_ROLLOUT.md`](docs/OTA_ROLLOUT.md) | Signed OTA manifests and the staged rollout with auto-halt. |
| [`docs/PACKAGING.md`](docs/PACKAGING.md) | The vendored `.deb` and the systemd unit. |
| [`docs/KNOWN_GAPS.md`](docs/KNOWN_GAPS.md) | What is deliberately not done yet, and why. |
| [`docs/adr/`](docs/adr/) | The design decisions, one file each. |

## Conventions

See [`CLAUDE.md`](CLAUDE.md): hardware behind `typing.Protocol` seams, pure logic with an injected
clock, `mypy --strict` and `ruff` clean, and determinism everywhere — no real sleep, no real clock,
seeded RNG.

## License

MIT — see `LICENSE`.
