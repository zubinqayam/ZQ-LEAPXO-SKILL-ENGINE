# scripts/build-windows.ps1 — LeapXO v9 Windows build script
# Builds the Python backend wheel, React frontend, and optional Tauri binary.
#
# Usage:
#   .\scripts\build-windows.ps1 [-Tauri] [-SkipTests]
#
# Environment variables:
#   LEAPXO_ENV      production | development (default: production)
#   PORT            Backend port (default: 8000)

param(
    [switch]$Tauri,
    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'

$env:LEAPXO_ENV = if ($env:LEAPXO_ENV) { $env:LEAPXO_ENV } else { 'production' }
$Port = if ($env:PORT) { $env:PORT } else { '8000' }

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "============================================================"
Write-Host "  LeapXO v9 — Windows Build"
Write-Host "  ENV=$($env:LEAPXO_ENV)  PORT=$Port  TAURI=$Tauri"
Write-Host "============================================================"

# ── Python backend ──────────────────────────────────────────────
Write-Host ""
Write-Host "▶ Installing Python dependencies..."
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet
python -m pip install fastapi uvicorn --quiet

Write-Host "▶ Building Python wheel..."
python -m pip install build --quiet
python -m build --wheel --outdir dist\python\ --quiet
Write-Host "  ✓ Wheel written to dist\python\"

# ── Run tests ───────────────────────────────────────────────────
if (-not $SkipTests) {
    Write-Host ""
    Write-Host "▶ Running pytest suite..."
    python -m pip install pytest pytest-asyncio pytest-cov --quiet
    python -m pytest tests/ -v --tb=short --cov=src --cov-report=term-missing
    Write-Host "  ✓ All tests passed"
}

# ── React frontend ───────────────────────────────────────────────
Write-Host ""
Write-Host "▶ Building React frontend..."
Set-Location frontend
npm ci --silent
npm run build
Set-Location $Root
Write-Host "  ✓ Frontend built to frontend\dist\"

# ── Tauri desktop binary (optional) ─────────────────────────────
if ($Tauri) {
    Write-Host ""
    Write-Host "▶ Building Tauri desktop binary..."
    Set-Location frontend
    npx tauri build
    Set-Location $Root
    Write-Host "  ✓ Tauri binary written to frontend\src-tauri\target\release\"
}

Write-Host ""
Write-Host "============================================================"
Write-Host "  Build complete ✓"
Write-Host "  Start backend: uvicorn backend.main:app --host 0.0.0.0 --port $Port"
Write-Host "  Serve frontend: cd frontend && npm run preview"
Write-Host "============================================================"
