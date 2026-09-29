# `tests/contract/` — telemetry contract self-test

This repo **owns** the telemetry contract (`contracts/telemetry.schema.json` + the AsyncAPI doc). The
API vendors a copy and validates every inbound message against it, so it matters that the device
actually emits payloads the schema accepts — otherwise the two repos agree on a document that the
device does not honour.

These tests take a real batch built by the agent's own `serde` + `build_batches` code and validate it
against the committed JSON Schema. They also prove the schema is strict (rejects a missing field, an
unknown field, an out-of-range value) and that the N-1 version rule holds (a v1 device is accepted by
a v2 server).

The **drift gate** (`scripts/check_contract.py`) is the other half: it checks the contract files
against their recorded checksums and, when the API repo is checked out, byte-compares them to the
API's vendored copy. Run it with `make contract-check`.
