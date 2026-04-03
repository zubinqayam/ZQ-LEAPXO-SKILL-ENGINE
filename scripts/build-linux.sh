#!/usr/bin/env bash
# scripts/build-linux.sh — LeapXO v9 Linux build script
# Builds the Python backend wheel, React frontend, and optional Tauri binary.
#
# Usage:
#   ./scripts/build-linux.sh [--tauri] [--skip-tests]
#
# Environment variables:
#   LEAPXO_ENV      production | development (default: production)
#   PORT            Backend port (default: 8000)
#   PYTHON          Python interpreter to use (default: python3)

set -euo pipefail

LEAPXO_ENV="${LEAPXO_ENV:-production}"
PORT="${PORT:-8000}"
PYTHON="${PYTHON:-python3}"
BUILD_TAURI=false
SKIP_TESTS=false

for arg in "$@"; do
  case $arg in
    --tauri)       BUILD_TAURI=true ;;
    --skip-tests)  SKIP_TESTS=true ;;
    *) echo "Unknown argument: $arg" >&2; exit 1 ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "============================================================"
echo "  LeapXO v9 — Linux Build"
echo "  ENV=$LEAPXO_ENV  PORT=$PORT  TAURI=$BUILD_TAURI"
echo "============================================================"

# ── Python backend ──────────────────────────────────────────────
echo ""
echo "▶ Installing Python dependencies..."
"$PYTHON" -m pip install --upgrade pip --quiet
"$PYTHON" -m pip install -r requirements.txt --quiet
"$PYTHON" -m pip install fastapi uvicorn --quiet

echo "▶ Building Python wheel..."
"$PYTHON" -m pip install build --quiet
"$PYTHON" -m build --wheel --outdir dist/python/ --quiet
echo "  ✓ Wheel written to dist/python/"

# ── Run tests ───────────────────────────────────────────────────
if [ "$SKIP_TESTS" = false ]; then
  echo ""
  echo "▶ Running pytest suite..."
  "$PYTHON" -m pip install pytest pytest-asyncio pytest-cov --quiet
  "$PYTHON" -m pytest tests/ -v --tb=short --cov=src --cov-report=term-missing
  echo "  ✓ All tests passed"
fi

# ── React frontend ───────────────────────────────────────────────
echo ""
echo "▶ Building React frontend..."
cd frontend
npm ci --silent
npm run build
cd "$ROOT"
echo "  ✓ Frontend built to frontend/dist/"

# ── Tauri desktop binary (optional) ─────────────────────────────
if [ "$BUILD_TAURI" = true ]; then
  echo ""
  echo "▶ Building Tauri desktop binary..."
  cd frontend
  npx tauri build
  cd "$ROOT"
  echo "  ✓ Tauri binary written to frontend/src-tauri/target/release/"
fi

echo ""
echo "============================================================"
echo "  Build complete ✓"
echo "  Start backend: uvicorn backend.main:app --host 0.0.0.0 --port $PORT"
echo "  Serve frontend: cd frontend && npm run preview"
echo "============================================================"
