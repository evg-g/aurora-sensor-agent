# Contributing to aurora-sensor-agent

## Setup

```bash
# WSL (Ubuntu-24.04)
make setup
```

Creates a `.venv` with [uv](https://docs.astral.sh/uv/) and installs the `dev` extras.
`uv.lock` is committed.

## Before you push

```bash
# WSL (Ubuntu-24.04)
make ci-local
```

Runs `ruff`, `mypy --strict`, and the test suite with coverage. The unit, driver-contract,
GPIO, serial, and fault tiers must all pass **with no hardware, no network, and no Docker**.

## Determinism rules (important for this repo)

- No real `sleep` — inject an awaitable delay.
- No real wall clock — inject a `Clock`.
- Seed every RNG.
- Every test must run on a laptop with no hardware. The `hil` (hardware-in-the-loop) tier is
  marked and deselected by default.

## Commits

[Conventional Commits](https://www.conventionalcommits.org/). Small, focused changes.
Non-obvious decisions get an ADR in `docs/adr/`.
