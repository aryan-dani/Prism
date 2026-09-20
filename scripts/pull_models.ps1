# Pull Ollama models for Prism.
# Default: the three models the product needs.
# Bench candidates: powershell -File scripts/pull_models.ps1 -All
#
# Safe to re-run; `ollama pull` no-ops if a model is already present.

param(
    [switch]$All
)

$ErrorActionPreference = "Stop"

$required = @(
    "nomic-embed-text",          # embeddings / routing (~274MB)
    "qwen2.5:7b-instruct",       # default generation (8GB sweet spot)
    "qwen2.5:3b-instruct"        # session titles (unloaded after each use)
)

$optional = @(
    "qwen3:8b",                     # bench candidate; slower, same recall on 12-Q pass
    "llama3.1:8b-instruct-q4_K_M",  # bench candidate 2
    "mistral:7b-instruct"           # bench candidate 3
)

$models = $required
if ($All) {
    $models = $required + $optional
    Write-Host "==> Pulling required models plus bench candidates" -ForegroundColor Cyan
} else {
    Write-Host "==> Pulling the three models Prism needs to run" -ForegroundColor Cyan
    Write-Host "    (bench candidates: powershell -File scripts/pull_models.ps1 -All)" -ForegroundColor DarkGray
}

foreach ($m in $models) {
    Write-Host "==> ollama pull $m" -ForegroundColor Cyan
    ollama pull $m
}

Write-Host "==> Installed models:" -ForegroundColor Green
ollama list
