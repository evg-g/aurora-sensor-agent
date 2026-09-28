# CI/CD for the sensor agent

Why this file exists: to explain, job by job, what each pipeline gate is *for* — the real failure it
catches — so that when a check goes red you know what it is protecting and where to look. Two
workflows: `ci.yml` (every PR and push to `main`) and `nightly.yml` (scheduled).

Every job sets `timeout-minutes`, the workflow sets a minimal `permissions: contents: read`, matrices
use `fail-fast: false`, and every workflow has `workflow_dispatch` so you can run it by hand.

## `ci.yml` — on pull request and push to main

| Job | What it runs | The failure it prevents |
|---|---|---|
| `lint` | `ruff check` + `ruff format --check` | style drift and dead code creeping in |
| `typecheck` | `mypy --strict` | a type error, an untyped seam, a signature that no longer matches |
| `test` | `pytest -m "not hil and not sil"` over **3.12 and 3.13** with coverage | a broken unit / logic / buffer / gpio / serial / fault / contract / fleet / soak tier, on both supported Pythons |
| `contract` | `scripts/check_contract.py` | the telemetry contract drifting from the API's vendored copy (see below) |
| `sil` | `pytest tests/sil -m sil` | the agent's real transports no longer lining up with the real API + broker |
| `package` | build wheel + `.deb` + a signed OTA manifest | a release artifact that does not build, or an OTA manifest that does not verify |

**Why hil and sil are excluded from `test`.** `hil` needs real hardware; `sil` needs Docker and the
API image. Keeping them out of the matrix means the core tiers stay fast and run anywhere, which is the
whole point of the Protocol seams.

**The contract job and cross-repo drift.** The device repo *owns* the telemetry contract; the API
vendors a copy. `check_contract.py` always runs the in-repo checksum guard. The cross-repo byte
compare only runs when the `API_REPO` variable is set (e.g. `owner/appointments-api`): the job then
checks out that repo and points `AURORA_API_REPO` at it. Without the variable the job runs the guard
only and stays green — so a fresh fork is not blocked on a sibling repo it does not have.

**The sil job and the API image.** SIL needs the built `appointments-api:local` image. When `API_REPO`
is set the job checks that repo out and `docker build`s the image; otherwise the SIL tests find no
image and **skip cleanly**. Either way the job passes — it never fails for lack of an input it was
never given.

**The package job and OTA signing.** It runs `scripts/build_deb.sh` (wheel + `.deb`) then
`scripts/ci_sign_ota.sh`, which signs a manifest for the wheel and verifies it before upload. It uses
the `OTA_PRIVATE_KEY` secret when present (a real release key) and otherwise generates an ephemeral
keypair, so the sign → verify flow is exercised on every PR even with no secrets configured. Artifacts
(wheel, sdist, `.deb`, `manifest.json`, public key) are uploaded with a retention period.

This "skip cleanly without inputs" pattern is deliberate and repo-wide: a fork with no secrets and no
sibling repo gets a fully green pipeline; the extra coverage switches on only where the inputs exist.

## `nightly.yml` — scheduled (03:00 UTC) and on demand

| Job | What it runs | Why nightly |
|---|---|---|
| `soak` | `pytest tests/soak` | seven simulated days is heavier than a per-PR gate; catches slow leaks |
| `flake` | the non-hil/non-sil suite **3×** (matrix) | a test that passes once but not thrice is flaky; find it here, not in a release |
| `hil` | `pytest -m hil` on a self-hosted runner | needs real hardware; gated behind the `HIL_ENABLED` variable so it is skipped entirely unless a wired device is available |

The `hil` job's `runs-on: [self-hosted, aurora-hil]` uses a custom label; `.github/actionlint.yaml`
declares it so `actionlint` does not flag it as unknown.

## Reproduce a gate locally

Every gate maps to a `make` target, so the exact commands run the same on your machine and in CI:

| `make` target | CI job |
|---|---|
| `make lint` | `lint` |
| `make typecheck` | `typecheck` |
| `make test` | `test` |
| `make contract-check` | `contract` |
| `make sil` | `sil` |
| `make deb` / `make package` | `package` |
| `make soak` | nightly `soak` |
| `make ci-local` | lint + typecheck + contract + test in one go |

## What `act` can and cannot run

`act` (run GitHub Actions locally) can drive `lint`, `typecheck`, `test`, `contract`, and `package`.
It cannot faithfully run `sil` (it needs Docker-in-Docker plus the pre-built API image) or `hil`
(real hardware / a self-hosted runner). Run those with `make sil` against your own Docker, and `hil`
on the wired device.

## Verify the workflow YAML

`actionlint` (installed at `~/.local/bin/actionlint`) checks both workflow files, including the shell
in `run:` steps. It is part of the repo's local checks; keep it clean.
