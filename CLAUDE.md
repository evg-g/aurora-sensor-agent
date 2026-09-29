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
make setup / make test / make lint / make typecheck / make ci-local
make contract-check  # telemetry-contract drift gate (checksums + cross-repo vs the API)
make sim     # run the SHT4x driver against the simulator (prints readings)
make run     # run the whole agent loop against the simulator (prints the health beacon)
make soak    # compressed seven-day soak test (fake clock, tracemalloc)
make fleet   # run the virtual device fleet from fleet.yaml
make rollout # staged OTA rollout across the fleet (BAD_BUILD=1 to demo the auto-halt)
make ota-demo# gen a key, sign a demo artifact, verify the OTA manifest end to end
make sil     # software-in-the-loop: agent vs Mosquitto + the API in Docker (needs the API image)
make deb / make wheel / make image / make package   # release artifacts
```

## Milestone 11 additions (transports, SIL, fleet, OTA, packaging)

- Real transports behind the `Transport` seam: `transport/mqtt.py` (paho, QoS 1, waits for PUBACK),
  `transport/http.py` (httpx, X-Device-Secret), `transport/fallback.py` (MQTT primary → HTTP).
- This repo **owns** the telemetry contract (`contracts/`); `scripts/check_contract.py` gates drift
  both in-repo (checksums) and cross-repo (vs the API's vendored copy). Self-test in `tests/contract/`.
- `fleet/` — `fleet.yaml` schema, the fleet simulator (`VirtualClock`, `SimUplink`), and
  `StagedRollout` (canary → 10% → fleet, auto-halt on rising error rate).
- `ota.py` — verify a signed Ed25519 manifest (signature → artifact hash/size → version direction)
  before applying. Sign with `scripts/build_ota_manifest.py`; no private keys are committed.
- SIL (`tests/sil/`, marked `sil`) needs Docker + `appointments-api:local`; skips cleanly otherwise.
  hil (`tests/hil/`, marked `hil`) is deselected by default and hardware-guarded.
- Packaging: `scripts/build_deb.sh` vendors the agent + deps under `/opt/aurora-sensor-agent/lib`.
