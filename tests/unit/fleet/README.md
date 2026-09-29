# `tests/unit/fleet/` — fleet simulator and staged-rollout tests

These prove the milestone-11 fleet pieces without any network or Docker:

- `test_config.py` — the `fleet.yaml` schema validates (duplicate ids, unknown cohort members are
  rejected) and `effective_profile` switches on update.
- `test_simulator.py` — a healthy virtual device publishes with a zero error rate; a dead-uplink
  device's error rate is 1.0; a bad-sensor device records read errors; runs are deterministic.
- `test_rollout.py` — a healthy update completes every cohort; a bad build is caught at the canary
  cohort and the rollout halts before the rest of the fleet gets it; `run_verified` refuses a
  tampered OTA manifest.

The real broker/API end-to-end fleet run is the SIL tier (`tests/sil/`), which needs Docker.
