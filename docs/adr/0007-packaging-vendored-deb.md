# 7. Package the agent as a self-contained .deb (plus a gateway image)

- Status: accepted
- Date: 2026-09-28

## Context

The field target is a Raspberry Pi running the agent as a `systemd` service (spec §7). It needs an
install artifact that works on a clinic network that may be slow or firewalled, and that does not
depend on PyPI being reachable at install time. The spec asks for "a wheel **and** a `.deb` (or a
Docker image for the gateway)"; we do all three.

The catch: the agent now depends on `cryptography`/`cffi`, which ship **compiled** wheels. So the
package cannot be pure-Python `Architecture: all`.

## Decision

**Vendor everything into the package.** `scripts/build_deb.sh` builds the wheel, then runs
`uv pip install --target staging/opt/aurora-sensor-agent/lib <wheel>` to install the agent *and every
runtime dependency* into one directory. The `.deb` ships that directory, a `systemd` unit, and an
env-file example. The service runs with `PYTHONPATH=/opt/aurora-sensor-agent/lib`, so **no network and
no pip run at install time** — `dpkg -i` is the whole install.

**Ship a hardened unit and a service user.** `postinst` creates an unprivileged `aurora` user, seeds
`/etc/aurora-sensor-agent/agent.env` from the example only if absent (an upgrade never clobbers device
credentials), and starts the service. The unit sets `NoNewPrivileges`, `ProtectSystem=strict`,
`ProtectHome`, `PrivateTmp`, and a `StateDirectory`. `prerm` stops and disables it. Both guard on
`/run/systemd/system`, so building or inspecting the package in a plain container never tries to talk
to systemd.

**Accept that the package is arch- and version-specific.** Because the compiled deps are built for the
build host's architecture and CPython 3.12, `control` declares `Architecture: <build arch>` and
`Depends: python3 (>= 3.12)`. A Pi build produces an arm64 package; an x86_64 build produces amd64.

**The Docker image is the alternative.** The same repo builds a gateway/fleet-simulator image
(`make image`); it is what the backend and web repos point their E2E and load tests at.

## Alternatives considered

| Option | Why not |
|---|---|
| `Architecture: all` pure-Python | false: `cryptography`/`cffi` are compiled, so the package is arch-specific whether we admit it or not |
| venv + `pip install` in `postinst` | needs PyPI (or a wheelhouse) reachable at install — exactly what a locked-down clinic network may not have |
| `fpm` | another toolchain (Ruby) to install and pin; `dpkg-deb` with a staging tree is already on the box and easy to read |

## Consequences

- Install is one offline command; the device needs no build tools and no internet.
- Cost: a separate `.deb` per architecture, and the target must have Python 3.12. Documented in
  `docs/PACKAGING.md`.
- Building and inspecting the package (`dpkg-deb -I` / `-c`) works on any Linux host, so CI verifies
  the artifact even though a full `systemd` install needs a real host (the Pi).
