# Exercises — break it on purpose

The device repo's whole promise is that hardware-facing code can be trusted **without hardware**. The
way to believe that is to break a safety check and watch the right test go red on a plain laptop —
no sensor, no network, no Docker.

Each exercise: read the **Break**, write down your **Prediction** (which command fails and why), make
the change, run the command under **Catch**, then **Restore** (`git checkout -- <file>`).

All commands run in `# WSL (Ubuntu-24.04)` from the `aurora-sensor-agent/` directory. Only the SIL
exercise needs Docker; everything else runs on a bare laptop. See `docs/HARDWARE_TESTING.md` for how
the tiers fit together.

Companion exercises: `appointments-api/docs/EXERCISES.md` and `appointments-web/docs/EXERCISES.md`.

---

## 1. Skip CRC validation in the SHT4x driver

**Break.** In `src/aurora_sensor_agent/drivers/sht4x.py`, stop verifying the CRC-8 on each 16-bit word
returned by the sensor — parse the bytes and skip the checksum comparison.

**Predict.** The I²C bus is a noisy two-wire line; a flipped bit turns 4.2 °C into 42 °C. What is the
CRC there to catch, and which test feeds the driver a corrupt frame?

**Catch (no hardware/Docker).**
```bash
make test
```

**Why.** Each SHT4x measurement word is followed by a CRC-8 (poly `0x31`, init `0xFF`) precisely so a
line glitch is detected rather than silently believed. The register-level unit test hands the driver a
frame with a deliberately wrong CRC and expects it to raise, not to return a bogus temperature. Skip
the check and that test fails. A bad reading that passes here becomes a false excursion — or a missed
one — downstream. See [ADR 0002](adr/0002-sht4x-register-level-driver-and-sim-replay.md).

**Restore.** `git checkout -- src/`

## 2. Make the excursion timer use the real clock

**Break.** In `src/aurora_sensor_agent/logic/excursion.py`, replace the injected timestamp with
`datetime.now(tz=UTC)` when measuring dwell/recovery, instead of using the `at` argument passed in.

**Predict.** The soak test compresses seven days into milliseconds by advancing a fake clock. What
happens to a dwell timer that ignores that clock and reads the wall clock instead?

**Catch (no hardware/Docker).**
```bash
make soak
make test          # the excursion unit tests too
```

**Why.** The excursion engine is a **pure function of `(timestamps, values, policy)`** — it never
reads a clock. That is what lets seven simulated days run in under a second and what lets the *server*
re-derive the exact same excursions from stored timestamps. Read the real clock and the dwell timer
never elapses in compressed time (an excursion that should raise never does), so the soak and the
timing unit tests fail. See [ADR 0003](adr/0003-excursion-state-machine-and-injected-clock.md).

**Restore.** `git checkout -- src/`

## 3. Remove the median filter

**Break.** In `src/aurora_sensor_agent/logic/filter.py`, return the raw latest sample instead of the
median-of-N.

**Predict.** One glitch sample slips through CRC by chance (a valid-looking but wrong reading). With a
median it is ignored; with the raw value it is believed. Which test encodes that?

**Catch (no hardware/Docker).**
```bash
make test
```

**Why.** A median, not an average, because one wild sample must not move the result — an average is
dragged by an outlier, a median ignores a lone one. The filter unit test injects a single spike into a
run of good samples and asserts the output does not jump. Return the raw value and it does. A
single-sample spike would otherwise start a spurious excursion.

**Restore.** `git checkout -- src/`

## 4. Make the store-and-forward buffer unbounded

**Break.** In `src/aurora_sensor_agent/buffer/sqlite.py`, remove the ring-buffer eviction (never drop
the oldest rows when the buffer is full).

**Predict.** A clinic loses its uplink for two days. On a Raspberry Pi Zero with a small SD card, what
happens to memory/disk, and which test simulates a long outage?

**Catch (no hardware/Docker).**
```bash
make soak
```

**Why.** The buffer is bounded on purpose: during a long outage it keeps the most recent readings and
drops the oldest, so a device never fills its disk and crashes. The soak test runs a two-day outage
inside the seven-day run and asserts the buffer stays bounded (and then drains cleanly when the uplink
returns). Remove eviction and the bounded-size assertion fails. See
[ADR 0004](adr/0004-store-and-forward-buffer-and-batching.md).

**Restore.** `git checkout -- src/`

## 5. Reuse the batch idempotency key — or stop reusing it

**Break.** In the batching/publish path, generate a **new** idempotency key each time a batch is
retried after a failure, instead of reusing the batch's stable key.

**Predict.** A batch is sent, the server commits it, but the ACK is lost, so the agent retries. If the
retry carries a fresh key, does the server see one batch or two?

**Catch (no hardware/Docker).**
```bash
uv run pytest tests/faults
```

**Why.** At-least-once delivery means retries happen; the device-generated key per batch is what makes
the server drop the duplicate. The fault-injection tier drops an ACK and asserts **no duplicate on the
server and no data loss**. A fresh key on retry breaks that guarantee — the server treats the retry as
a new batch. See [ADR 0004](adr/0004-store-and-forward-buffer-and-batching.md).

**Restore.** `git checkout -- src/`

## 6. Drift the telemetry contract

**Break.** Add or rename a field in `contracts/telemetry.schema.json` (the payload schema the device
**owns**) without regenerating/aligning the API's vendored copy.

**Predict.** The API validates every inbound message against its vendored copy of this schema. Which
gate fires, and in which repo, when the two copies disagree?

**Catch (no hardware/Docker).**
```bash
make contract-check
```

**Why.** The device owns the telemetry contract; the API vendors it byte-for-byte and validates
messages against it. The drift gate (`scripts/check_contract.py`) checksums the schema and
byte-compares it against the API's vendored copy — change one side only and it fails. This is the
OpenAPI gate in reverse: the device is the producer here. Also confirm the self-test still builds a
valid batch: `uv run pytest tests/contract`. See
[ADR 0005](adr/0005-device-transports-and-sil.md) and the API's
[CONTRACT_WORKFLOW.md](../../appointments-api/docs/CONTRACT_WORKFLOW.md).

**Restore.** `git checkout -- contracts/`

## 7. Make the simulator non-deterministic

**Break.** In `src/aurora_sensor_agent/sim/` (the thermal model or the RNG setup), drop the fixed seed
so the simulator produces different noise on every run.

**Predict.** The driver-contract suite runs the **same** behavioural tests against `sim` and `replay`
and expects them to agree. What happens to `replay` (a byte-for-byte recording of a *seeded* sim run)
when the sim is no longer seeded?

**Catch (no hardware/Docker).**
```bash
uv run pytest tests/driver_contract
```

**Why.** Substitutability is the whole lesson: `real`, `sim`, and `replay` satisfy one protocol and
one behavioural suite, so a test written once runs against all three. `replay` reproduces a recorded
seeded run exactly; an unseeded sim diverges from its own recording, and the contract suite (and any
replay assertion) fails. Determinism is not a nicety here — it is what makes the recorded regression
fixtures meaningful. See [ADR 0002](adr/0002-sht4x-register-level-driver-and-sim-replay.md).

**Restore.** `git checkout -- src/`

## 8. Trust the SIL end-to-end path, then break it (needs Docker)

**Break.** Point the agent's HTTP transport at the wrong path (e.g. change the batch endpoint URL in
`src/aurora_sensor_agent/transport/http.py`), or send the wrong `X-Device-Secret`.

**Predict.** The SIL tier runs the real agent against a real broker and the real API image in
containers. Which end of the pipe complains — the transport, or the read-back assertion?

**Catch (needs Docker + the API image).**
```bash
make sil
```

**Why.** SIL is the only tier with no doubles: the agent's real MQTT and HTTP transports drive
telemetry into a real `appointments-api` container, and the test reads it back through the API's
time-series. A wrong endpoint or a bad secret means the readings never land, so the read-back
assertion finds an empty series. (If the API image is stale or Docker is off, SIL skips cleanly rather
than lying — see the note in `docs/KNOWN_GAPS.md`.) See [ADR 0005](adr/0005-device-transports-and-sil.md).

**Restore.** `git checkout -- src/`
