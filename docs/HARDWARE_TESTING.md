# Testing hardware code with no hardware

Why this file exists: this agent runs on a Raspberry Pi wired to a temperature sensor, but almost
none of its tests need a Pi, a sensor, a network, or Docker. This explains how, using what is built
through milestone 8. Later tiers (GPIO, serial, the full fault catalogue, soak, hardware-in-the-loop)
are added in the milestones noted at the end.

## The one idea

Every place the code touches the outside world is a `typing.Protocol` — a promise about the *shape*
of an object, not its identity (see `src/aurora_sensor_agent/protocols.py` and ADR 0001). Anything
with matching methods satisfies it. So the same code runs against real hardware, a simulator, or a
recorded trace, and a test just picks which one to hand in.

Analogy: a Protocol is a wall socket. The driver is an appliance with a plug. Real hardware, the
simulator, and the replay trace are three different things you can plug into the same socket — the
appliance neither knows nor cares which.

The six seams: `I2CBus`, `SerialPort`, `GpioPin`, `Clock`, `Transport`, `BufferStore`. Milestone 8
implements and exercises `I2CBus` and `Clock`; the other four are defined here as the agreed
contracts and implemented in milestones 9-11.

## The sensor, at the register level

`Sht4xDriver` (`drivers/sht4x.py`) speaks the actual SHT4x wire protocol rather than a convenient
abstraction, because the wire is where the interesting failures live:

1. Write a one-byte command (`0xFD` = measure, high precision).
2. Wait the conversion time (~8.3 ms). Read too early and a real chip NACKs.
3. Read six bytes: two 16-bit words, each followed by its own **CRC-8** (`protocol/crc.py`).
4. Verify both checksums, then convert:
   - `T[°C]  = -45 + 175 * raw_t  / 65535`
   - `RH[%]  =  -6 + 125 * raw_rh / 65535`, clamped to `0..100`.

Testing this directly (`tests/unit/protocol/test_sht4x_driver.py`) proves the command bytes, the
timing wait, word parsing, endianness, CRC acceptance *and rejection*, the conversion at the rails,
and out-of-range raw handling — all with a scripted fake bus that hands back bytes we choose.

### What a CRC protects against

The CRC-8 is a checksum byte the chip appends to each word. Flip a bit anywhere on the I²C wire and
the recomputed CRC no longer matches, so the driver *rejects* the reading instead of silently
trusting a corrupted temperature. `test_measure_rejects_corrupted_crc` flips a bit and asserts the
driver raises. This is the difference between a loud, catchable error and a bad number reaching the
cold-chain alerting engine.

## Simulator vs replay

| | Simulator (`sim/`) | Replay (`replay/`) |
|---|---|---|
| Where readings come from | A seeded fridge `ThermalModel` (setpoint, door-open warm-ups, noise, drift) | Fixed bytes recorded earlier |
| Good for | Exploring behaviour, injecting faults, generating data | Reproducing one exact scenario forever |
| Determinism | Same seed + same time → same reading | Byte-for-byte, on any machine |

The simulator is a **register-level chip model**: it accepts the same command bytes, enforces the
same conversion delay, and returns properly framed 6-byte responses with real CRCs. The unmodified
driver runs against it. Because it is pure in time (`sample(t)` depends only on `t` and the seed), a
run can be captured into a trace and replayed exactly — that is what `scripts/record_trace.py` does,
writing `tests/fixtures/traces/sim_baseline.jsonl`.

Run the simulator yourself:

```bash
# WSL (Ubuntu-24.04)
make sim                 # 10 readings from the simulated sensor
uv run aurora-agent sim --count 5 --interval 0 --seed 3
```

## Fault injection (chip/bus level)

The simulated bus can inject the failures a real sensor throws at you, at a chosen measurement index
(`sim/faults.py`, tested in `tests/unit/sim/test_faults.py`):

| Fault | What the driver must do |
|---|---|
| `BAD_CRC` | Reject the reading (`CrcError`), then succeed on the next one |
| `NACK` | Raise `OSError` on the command write, then recover |
| `TIMEOUT` | Raise `TimeoutError`, then recover |
| `SHORT_READ` | Reject a frame with too few bytes |
| `POWER_LOSS` | Raise, and leave the bus dead until reopened |
| `STUCK` | Notice the value never changes (frozen frame) |

Most faults are one-shot (a transient glitch) so a retry succeeds — that is what the backoff layer in
milestone 9 relies on. The higher-layer faults (NaN in the pipeline, disk full, clock jump) live at
the buffer/clock seams and are injected there in milestone 9.

## The driver contract suite

`tests/driver_contract/` holds one behavioural suite (`Sht4xStackContract`) and runs it against each
bus. `sim` and `replay` run everywhere; `real` is skipped unless a Pi with an SHT4x is wired up, but
the class still documents exactly what the real bus must satisfy. A separate test proves the real bus
imports and constructs with no `smbus2` installed — its hardware imports are lazy, deferred to the
first actual read.

## What runs where

| Tier | Needs hardware? | Needs Docker/network? | Milestone |
|---|---|---|---|
| Register-level unit (`tests/unit/protocol/`) | No | No | 8 |
| Simulator + fault injection (`tests/unit/sim/`) | No | No | 8 |
| Driver contract (`tests/driver_contract/`) | No (real tier skipped) | No | 8 |
| Logic unit — excursion state machine, filters (`tests/unit/logic/`) | No | No | 9 |
| GPIO (`tests/unit/gpio/`) | No (`gpiozero` MockFactory) | No | 9 |
| Serial (`tests/unit/serial/`) | No (`loop://` + `pty`) | No | 9 |
| Full fault catalogue (`tests/faults/`) | No | No | 9 |
| Soak (`tests/soak/`) | No (fake clock) | No | 9 |
| Software-in-the-loop (`tests/sil/`) | No | Yes (testcontainers) | 11 |
| Hardware-in-the-loop (`tests/hil/`) | Yes | — | 11 (deselected by default) |
