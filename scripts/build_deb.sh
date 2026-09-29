#!/usr/bin/env bash
# Build a .deb that installs the agent + its Python dependencies and a systemd unit.
#
# The agent and every runtime dependency are vendored under /opt/aurora-sensor-agent/lib (installed
# with `uv pip install --target`), so the package needs no network at install time. The service runs
# with PYTHONPATH pointing there. Because cryptography/cffi ship compiled wheels, the package is
# architecture-specific (the build host's arch) and targets Python 3.12; see docs/PACKAGING.md.
set -euo pipefail

cd "$(dirname "$0")/.."  # repo root
UV="${UV:-uv}"

VERSION="$($UV run python -c 'import importlib.metadata as m; print(m.version("aurora-sensor-agent"))')"
ARCH="$(dpkg --print-architecture)"
STAGING="staging/deb"
DEB="dist/aurora-sensor-agent_${VERSION}_${ARCH}.deb"

echo ">> building wheel"
rm -rf "$STAGING"
mkdir -p dist
$UV build --wheel --out-dir dist

echo ">> assembling staging tree"
mkdir -p "$STAGING/DEBIAN" \
    "$STAGING/opt/aurora-sensor-agent/lib" \
    "$STAGING/lib/systemd/system" \
    "$STAGING/etc/aurora-sensor-agent"

echo ">> vendoring the agent + dependencies"
WHEEL="$(ls -t dist/aurora_sensor_agent-*.whl | head -1)"
$UV pip install --target "$STAGING/opt/aurora-sensor-agent/lib" "$WHEEL"
rm -f "$STAGING/opt/aurora-sensor-agent/lib/.lock"  # uv's target lock, not needed in the package

cp packaging/systemd/aurora-sensor-agent.service "$STAGING/lib/systemd/system/"
cp packaging/agent.env.example "$STAGING/etc/aurora-sensor-agent/agent.env.example"
sed -e "s/@VERSION@/${VERSION}/" -e "s/@ARCH@/${ARCH}/" packaging/deb/control.in \
    > "$STAGING/DEBIAN/control"
install -m 0755 packaging/deb/postinst "$STAGING/DEBIAN/postinst"
install -m 0755 packaging/deb/prerm "$STAGING/DEBIAN/prerm"

echo ">> building package"
dpkg-deb --build --root-owner-group "$STAGING" "$DEB"

echo ">> done: $DEB"
dpkg-deb -I "$DEB"
echo "---- top-level contents ----"
dpkg-deb -c "$DEB" | grep -E ' \./(etc|lib|opt)/[^/]*/?$' || true
