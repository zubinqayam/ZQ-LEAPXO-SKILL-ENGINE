#!/usr/bin/env bash
# scripts/test-all.sh — LeapXO v9 full test runner
#
# Usage:
#   ./scripts/test-all.sh [--coverage] [--fail-fast]
#
# Environment:
#   PYTHON    Python interpreter (default: python3)

set -euo pipefail

COVERAGE=false
FAIL_FAST=false

for arg in "$@"; do
  case $arg in
    --coverage)  COVERAGE=true ;;
    --fail-fast) FAIL_FAST=true ;;
    *) echo "Unknown argument: $arg" >&2; exit 1 ;;
  esac
done

PYTHON="${PYTHON:-python3}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "============================================================"
echo "  LeapXO v9 — Full Test Suite"
echo "============================================================"

# ── Install dependencies ─────────────────────────────────────────
echo ""
echo "▶ Installing test dependencies..."
"$PYTHON" -m pip install -r requirements.txt --quiet
"$PYTHON" -m pip install fastapi uvicorn httpx pytest-asyncio --quiet

# ── pytest flags ─────────────────────────────────────────────────
PYTEST_ARGS="-v --tb=short"
[ "$FAIL_FAST" = true ] && PYTEST_ARGS="$PYTEST_ARGS -x"
[ "$COVERAGE" = true ]  && PYTEST_ARGS="$PYTEST_ARGS --cov=src --cov=backend --cov-report=term-missing --cov-report=xml:coverage.xml"

echo ""
echo "▶ Running pytest..."
"$PYTHON" -m pytest tests/ $PYTEST_ARGS

RESULT=$?

echo ""
if [ $RESULT -eq 0 ]; then
  echo "  ✓ All tests passed"
  [ "$COVERAGE" = true ] && echo "  ✓ Coverage report written to coverage.xml"
else
  echo "  ✗ Some tests failed (exit code $RESULT)"
fi

echo "============================================================"
exit $RESULT
