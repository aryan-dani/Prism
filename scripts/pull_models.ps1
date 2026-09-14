# Pulls every Ollama model Prism needs (generation candidates + embedding + title model).
# Safe to re-run; `ollama pull` no-ops if a model is already present.

$ErrorActionPreference = "Stop"

$models = @(
    "nomic-embed-text",          # embedding model (CPU/GPU-light, ~274MB)
    "qwen2.5:7b-instruct",       # default generation model (8GB sweet spot)
    "qwen3:8b",                  # generation candidate (benchmarked; slower, same recall on 12-Q pass)
    "qwen2.5:3b-instruct",       # cheap session-titling model (already local)
    "llama3.1:8b-instruct-q4_K_M", # generation candidate 2
    "mistral:7b-instruct"        # generation candidate 3
)

foreach ($m in $models) {
    Write-Host "==> ollama pull $m" -ForegroundColor Cyan
    ollama pull $m
}

Write-Host "==> Installed models:" -ForegroundColor Green
ollama list
