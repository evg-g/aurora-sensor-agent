# Known gaps and deliberate limitations

Why this file exists: to record, honestly, what the agent does *not* do and where the current design
takes a shortcut, so nobody is surprised later. These are conscious trade-offs, not bugs.

## Milestone 11 (device SIL + CI/CD)

- **SIL needs Docker and the API image.** `tests/sil/` requires a running Docker and the built
  `appointments-api:local` image. Without either it skips cleanly, so it does not run in the plain
  `make test` gate — only in `make sil` and the CI `sil` job (which builds the image when `API_REPO`
  is configured). A fork without the sibling repo gets a green pipeline but no SIL coverage.

- **MQTT auth trusts the broker, not a per-message secret.** On the MQTT path the API worker takes the
  device id from the topic and relies on the broker's ACLs to bind a device to its own topic. There is
  no per-message device secret (MQTT has no per-request header). This matches the milestone-10 worker
  by design; the HTTP fallback path *does* carry the per-device `X-Device-Secret`. A production broker
  must be configured with per-device credentials and topic ACLs for this to be safe; the SIL broker
  allows anonymous access for the test only.

- **A 4xx from the HTTP transport is retried.** `HttpTransport` raises on any non-2xx so nothing is
  silently dropped, and it logs a non-429 4xx at error level, but the agent's drain loop treats every
  raised `ConnectionError` as retryable and keeps the readings buffered. Payloads are contract-validated
  before they are sent, so in practice a 4xx means a credential problem — which retrying will not fix on
  its own. A dedicated "permanent failure" path (drop + alarm instead of retry) is a follow-up.

- **The `.deb` is architecture- and Python-3.12-specific.** `cryptography`/`cffi` ship compiled wheels,
  so the vendored package is built for the build host's architecture and CPython 3.12. Build it on the
  target architecture; the target needs `python3 (>= 3.12)`. See `docs/PACKAGING.md`.

- **The packaged service runs the simulator loop.** The shipped `systemd` unit's `ExecStart` runs
  `aurora-agent run`, which drives the *simulated* fridge, so the service is exercisable the moment it
  installs. Wiring the run to a real SHT4x over real I²C is the hardware-in-the-loop concern
  (`tests/hil/`, `docs/HARDWARE_TESTING.md`); the operator points `ExecStart`/`agent.env` at the real
  sensor on a wired device.

- **OTA verification, not OTA application.** The agent verifies an update (signature, integrity,
  version) but does not itself perform the swap; replacing the package and restarting the service is the
  `.deb`/systemd concern (ADR 0007). The end-to-end "download → verify → swap → restart" agent flow is
  intentionally out of scope for this milestone.

- **Rollback is a deliberate re-pin.** The version-direction check refuses a downgrade, so a rollback
  is done by re-pinning the previous signed release to the affected devices, not by installing an older
  build behind the agent's back. See `docs/OTA_ROLLOUT.md`.

- **`testcontainers` log-wait deprecation.** The SIL fixture uses `wait_for_logs` with string
  predicates, which the installed `testcontainers` version warns is deprecated. It is functional; moving
  to the structured `LogMessageWaitStrategy` API is a tidy-up.
