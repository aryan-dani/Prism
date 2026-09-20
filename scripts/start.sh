#!/usr/bin/env bash
# Start Prism API + Vite UI (Linux/macOS). For Windows use start.ps1 / scripts/start.ps1.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if curl -sf --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null; then
  echo "Ollama is already running on :11434"
elif command -v ollama >/dev/null 2>&1; then
  echo "Starting Ollama on :11434 ..."
  ollama serve >/tmp/prism-ollama.log 2>&1 &
  for _ in $(seq 1 20); do
    if curl -sf --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null; then
      echo "Ollama is up"
      break
    fi
    sleep 0.5
  done
else
  echo "Ollama is not installed. Chat will show API degraded until it is running."
fi

cd "$ROOT/backend"
uv run uvicorn prism.api.main:app --reload --port 8000 &
API_PID=$!
cd "$ROOT/frontend"
npm run dev -- --host 127.0.0.1 --port 5173 &
UI_PID=$!
trap 'kill $API_PID $UI_PID 2>/dev/null || true' EXIT
echo "API http://127.0.0.1:8000  UI http://127.0.0.1:5173"
echo "Login: alex.employee@prism.local / Prism2026!"
wait
