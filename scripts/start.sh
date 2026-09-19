#!/usr/bin/env bash
# Start Prism API + Vite UI (Linux/macOS). For Windows use start.ps1 / scripts/start.ps1.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
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
