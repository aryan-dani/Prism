# Prism one-shot environment setup (Windows / PowerShell)
# Usage: powershell -ExecutionPolicy Bypass -File scripts/setup.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "==> Syncing Python environment in backend/ with uv" -ForegroundColor Cyan
Push-Location "$root\backend"
uv sync
Pop-Location

Write-Host "==> Pulling required Ollama models" -ForegroundColor Cyan
& "$PSScriptRoot\pull_models.ps1"

Write-Host "==> Installing frontend/ dependencies" -ForegroundColor Cyan
if (Test-Path "$root\frontend\package.json") {
    Push-Location "$root\frontend"
    npm install
    Pop-Location
} else {
    Write-Host "   (frontend/ not found, skipping)" -ForegroundColor Yellow
}

Write-Host "==> Building (or rebuilding) the local Chroma + BM25 index" -ForegroundColor Cyan
Push-Location "$root\backend"
uv run python -m prism.ingest.build_index
Pop-Location

Write-Host "==> Setup complete." -ForegroundColor Green
Write-Host "Next steps:"
Write-Host "  powershell -File scripts/start.ps1   # or simply: .\start.ps1"
