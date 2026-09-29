#!/usr/bin/env bash
# Sign and verify an OTA manifest for the built wheel, for the CI package job.
#
# Uses the release private key from $OTA_PRIVATE_KEY when set (a CI secret), otherwise generates an
# ephemeral keypair so the sign -> verify flow is exercised on every PR. The artifact is always
# verified against the public key before it is uploaded.
set -euo pipefail

UV="${UV:-uv}"
mkdir -p keys dist

if [ -n "${OTA_PRIVATE_KEY:-}" ]; then
    printf '%s' "${OTA_PRIVATE_KEY}" > keys/ota_private.pem
    $UV run python scripts/derive_ota_pubkey.py keys/ota_private.pem keys/ota_public.pem
else
    $UV run python scripts/gen_ota_key.py
fi

WHEEL="$(ls -t dist/aurora_sensor_agent-*.whl | head -1)"
VERSION="$($UV run python -c 'import importlib.metadata as m; print(m.version("aurora-sensor-agent"))')"

$UV run python scripts/build_ota_manifest.py --artifact "$WHEEL" \
    --version "$VERSION" --private-key keys/ota_private.pem --out dist/manifest.json
$UV run python scripts/build_ota_manifest.py --verify --artifact "$WHEEL" \
    --manifest dist/manifest.json --public-key keys/ota_public.pem --current-version 0.0.0
