#!/usr/bin/env bash
# Fail-closed proof that a WAIKE client release binary embeds frontendDist
# (custom-protocol), rather than relying on Vite devUrl http://localhost:1420.
#
# Usage:
#   scripts/smoke_embedded_frontend_dist.sh <binary> <frontend_dist_dir>
#
# UI strings inside Vite JS bundles are often brotli/gzip compressed inside the
# ELF, so plaintext `strings | grep "Sign in..."` is not a reliable embed proof.
# This smoke instead:
#   1) Requires the built dist to contain the login UI marker (shipped UI truth)
#   2) Requires the binary to contain built asset path/filename keys (embed truth)
#   3) Fails closed if localhost:1420 is present without embed proof
set -euo pipefail

BIN="${1:-}"
DIST="${2:-}"

if [ -z "$BIN" ] || [ -z "$DIST" ]; then
  echo "FATAL: usage: $0 <binary> <frontend_dist_dir>" >&2
  exit 2
fi

if [ ! -f "$BIN" ]; then
  echo "FATAL: missing binary: $BIN" >&2
  exit 1
fi

if [ ! -d "$DIST" ]; then
  echo "FATAL: missing frontend dist dir: $DIST" >&2
  exit 1
fi

LOGIN_MARKER="Sign in to your school hub session"
if ! grep -R -F -q -- "$LOGIN_MARKER" "$DIST"; then
  echo "FATAL: login UI marker missing from frontend dist ($DIST)" >&2
  echo "       expected substring: $LOGIN_MARKER" >&2
  exit 1
fi
echo "OK: frontend dist contains login UI marker"

if [ ! -f "$DIST/index.html" ]; then
  echo "FATAL: missing $DIST/index.html" >&2
  exit 1
fi

ASSET_COUNT="$(find "$DIST" -type f \( -name '*.js' -o -name '*.css' -o -name 'index.html' \) | wc -l | tr -d ' ')"
if [ "$ASSET_COUNT" -lt 2 ]; then
  echo "FATAL: frontend dist looks incomplete (need index.html + hashed assets)" >&2
  exit 1
fi

EMBED_HITS=0
EMBED_PROOF=""

# Prefer hashed Vite asset basenames; index.html alone is a weak signal.
while IFS= read -r asset; do
  [ -n "$asset" ] || continue
  base="$(basename "$asset")"
  if [ "$base" = "index.html" ]; then
    continue
  fi
  if grep -a -F -q -- "$base" "$BIN"; then
    EMBED_HITS=$((EMBED_HITS + 1))
    EMBED_PROOF="$base"
    echo "OK: binary embeds frontend asset key: $base"
  fi
done <<EOF
$(find "$DIST" -type f \( -name '*.js' -o -name '*.css' -o -name 'index.html' \) | sort)
EOF

if [ "$EMBED_HITS" -lt 1 ]; then
  # Secondary: relative path forms Tauri often stores (assets/index-….js).
  while IFS= read -r asset; do
    [ -n "$asset" ] || continue
    rel="${asset#"$DIST"/}"
    if [ "$rel" = "index.html" ]; then
      continue
    fi
    if grep -a -F -q -- "$rel" "$BIN"; then
      EMBED_HITS=$((EMBED_HITS + 1))
      EMBED_PROOF="$rel"
      echo "OK: binary embeds frontend asset path: $rel"
    fi
  done <<EOF
$(find "$DIST" -type f \( -name '*.js' -o -name '*.css' -o -name 'index.html' \) | sort)
EOF
fi

HAS_DEVURL=0
if grep -a -F -q 'http://localhost:1420' "$BIN"; then
  HAS_DEVURL=1
fi

if [ "$EMBED_HITS" -lt 1 ]; then
  echo "FATAL: frontendDist asset keys missing from release binary (custom-protocol embed failed?)" >&2
  if [ "$HAS_DEVURL" -eq 1 ]; then
    echo "FATAL: binary still references http://localhost:1420 without embedded frontendDist" >&2
  fi
  exit 1
fi

if [ "$HAS_DEVURL" -eq 1 ]; then
  echo "NOTE: tauri.conf.json devUrl string still present in binary (config embed); embed proof OK via $EMBED_PROOF"
fi

echo "OK: embedded frontendDist smoke passed (asset_hits=$EMBED_HITS proof=$EMBED_PROOF)"
