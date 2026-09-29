# Packaging the agent

Why this file exists: the agent runs on a Raspberry Pi as a `systemd` service, and it must install on
a clinic network that may be slow or firewalled. This explains the three artifacts we build and how to
install the `.deb` on a real device. The design reasoning is in ADR 0007.

## The three artifacts

| Command | Output | Use |
|---|---|---|
| `make wheel` | `dist/*.whl` + `dist/*.tar.gz` | the Python package; also what the OTA manifest signs |
| `make deb` | `dist/aurora-sensor-agent_<version>_<arch>.deb` | the field install for a Pi |
| `make image` | `aurora-sensor-agent:local` Docker image | the gateway / fleet-simulator container |
| `make package` | wheel + sdist + `.deb` | everything a release needs |

## What the `.deb` contains

`scripts/build_deb.sh` builds the wheel, then vendors the agent **and every runtime dependency** into
one directory with `uv pip install --target`. So the package is self-contained — no pip, no PyPI, no
network at install time.

```
/opt/aurora-sensor-agent/lib/                 # the agent + all deps (import path)
/lib/systemd/system/aurora-sensor-agent.service
/etc/aurora-sensor-agent/agent.env.example
```

`postinst` creates the unprivileged `aurora` user, copies `agent.env.example` to `agent.env` only if it
does not already exist (an upgrade never overwrites device credentials), and starts the service.
`prerm` stops and disables it.

## Build it

```bash
# WSL (Ubuntu-24.04) — or any Linux with uv + dpkg-deb
make deb
```

Inspect the result anywhere, no install needed:

```bash
# WSL
dpkg-deb -I dist/aurora-sensor-agent_*.deb    # control metadata
dpkg-deb -c dist/aurora-sensor-agent_*.deb    # file list
```

## Install it on a device

```bash
# on the Pi
sudo dpkg -i aurora-sensor-agent_<version>_<arch>.deb
sudoedit /etc/aurora-sensor-agent/agent.env    # device id, clinic id, broker/API URLs
sudo systemctl restart aurora-sensor-agent
systemctl status aurora-sensor-agent
journalctl -u aurora-sensor-agent -f
```

The unit's `ExecStart` runs the agent loop (`aurora-agent run`) under the `aurora` user, restarts on
failure, and is sandboxed (`NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp`, a
`StateDirectory`). For a real sensor you point the run at the hardware wiring; the shipped demo unit
runs against the simulator loop so the service is exercisable out of the box.

## Architecture and Python version

The package is **not** `Architecture: all`. `cryptography`/`cffi` ship compiled wheels, so the vendored
deps are built for the build host's architecture and for CPython 3.12. That means:

- build the `.deb` **on the target architecture** (build on a Pi, or an arm64 runner, for arm64 devices;
  an x86_64 build produces an amd64 package),
- the target must have `python3 (>= 3.12)` — declared in `Depends`.

## Corporate/TLS-inspecting networks

The `Dockerfile` supports the optional `EXTRA_CA_CERT` build arg (see the top-level
`docs/CORPORATE_NETWORK.md` in the API repo for the pattern); it is off the default path and never
required on a clean network.
