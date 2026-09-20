# Rebuild Prism Chroma + BM25 index from data/processed/*.jsonl
# Fails loudly if any required domain JSONL is missing or empty.
#
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File scripts/rebuild_index.ps1
#   .\scripts\rebuild_index.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$processed = Join-Path $backend "data\processed"

$required = @(
    "customer_support.jsonl",
    "privacy.jsonl",
    "legal_from_assist.jsonl",
    "legal_from_kohler.jsonl",
    "hr.jsonl",
    "finance.jsonl",
    "hr_records.jsonl",
    "finance_compensation.jsonl",
    "legal_warranty_fixture.jsonl"
)

Write-Host "==> Checking required processed JSONL files" -ForegroundColor Cyan
if (-not (Test-Path $processed)) {
    Write-Host "ERROR: processed dir not found: $processed" -ForegroundColor Red
    exit 1
}

$failed = $false
foreach ($name in $required) {
    $path = Join-Path $processed $name
    if (-not (Test-Path $path)) {
        Write-Host "  MISSING  $name" -ForegroundColor Red
        $failed = $true
        continue
    }
    $lines = @(Get-Content -Path $path -ErrorAction Stop | Where-Object { $_.Trim() -ne "" }).Count
    if ($lines -lt 1) {
        Write-Host "  EMPTY    $name (0 records)" -ForegroundColor Red
        $failed = $true
    } else {
        Write-Host "  OK       $name ($lines lines)" -ForegroundColor Green
    }
}

if ($failed) {
    Write-Host ""
    Write-Host "Rebuild aborted. Fix missing/empty files, then re-run." -ForegroundColor Red
    Write-Host "Typical recovery:" -ForegroundColor Yellow
    Write-Host "  cd backend"
    Write-Host "  uv run python -m prism.ingest.crawl_assist"
    Write-Host "  uv run python -m prism.ingest.parse_kohler_legal"
    Write-Host "  uv run python -m prism.ingest.build_synthetic"
    exit 1
}

Write-Host ""
Write-Host "==> Building Chroma + BM25 index" -ForegroundColor Cyan
Push-Location $backend
try {
    uv run python -m prism.ingest.build_index
    if ($LASTEXITCODE -ne 0) {
        throw "build_index exited with code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "==> Rebuild complete." -ForegroundColor Green
