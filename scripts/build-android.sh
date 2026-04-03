#!/usr/bin/env bash
# scripts/build-android.sh — LeapXO v9 Android (Tauri Mobile) build script
#
# Prerequisites:
#   - Android Studio + NDK installed
#   - ANDROID_HOME environment variable set
#   - Java 17+ in PATH
#   - Rust with android targets: rustup target add aarch64-linux-android armv7-linux-androideabi
#   - Tauri CLI 2.x installed globally: npm install -g @tauri-apps/cli
#
# Usage:
#   ./scripts/build-android.sh [--release] [--skip-tests]
#
# The APK / AAB is written to:
#   frontend/src-tauri/gen/android/app/build/outputs/

set -euo pipefail

RELEASE_MODE=false
SKIP_TESTS=false

for arg in "$@"; do
  case $arg in
    --release)     RELEASE_MODE=true ;;
    --skip-tests)  SKIP_TESTS=true ;;
    *) echo "Unknown argument: $arg" >&2; exit 1 ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "============================================================"
echo "  LeapXO v9 — Android Build"
echo "  RELEASE=$RELEASE_MODE"
echo "============================================================"

# ── Validate prerequisites ───────────────────────────────────────
if [ -z "${ANDROID_HOME:-}" ]; then
  echo "ERROR: ANDROID_HOME is not set." >&2
  exit 1
fi

for cmd in java rustc cargo node npm; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "ERROR: '$cmd' not found in PATH." >&2
    exit 1
  fi
done

echo "  ✓ Prerequisites verified"

# ── Run backend tests ────────────────────────────────────────────
if [ "$SKIP_TESTS" = false ]; then
  echo ""
  echo "▶ Running pytest suite..."
  python3 -m pip install -r requirements.txt --quiet
  python3 -m pip install fastapi uvicorn --quiet
  python3 -m pytest tests/ -v --tb=short
  echo "  ✓ All tests passed"
fi

# ── Install frontend dependencies ────────────────────────────────
echo ""
echo "▶ Installing frontend dependencies..."
cd frontend
npm ci --silent

# ── Tauri Android init (idempotent) ─────────────────────────────
if [ ! -d "src-tauri/gen/android" ]; then
  echo "▶ Initialising Tauri Android target..."
  npx tauri android init
fi

# ── Build ────────────────────────────────────────────────────────
echo ""
if [ "$RELEASE_MODE" = true ]; then
  echo "▶ Building Android APK/AAB (release)..."
  npx tauri android build --apk
  echo "  ✓ Release APK written to src-tauri/gen/android/app/build/outputs/"
else
  echo "▶ Building Android APK (debug)..."
  npx tauri android build --apk --debug
  echo "  ✓ Debug APK written to src-tauri/gen/android/app/build/outputs/"
fi

cd "$ROOT"

echo ""
echo "============================================================"
echo "  Android build complete ✓"
echo "============================================================"
