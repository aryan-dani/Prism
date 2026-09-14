# Prism stress harness

Adversarial / multi-turn evaluation against a live API.

## Run

```powershell
# Terminal 1 — API
cd backend
uv run uvicorn prism.api.main:app --port 8000

# Terminal 2 — harness (sequential; do not parallelize on 8GB VRAM)
cd backend
uv run python -m eval.stress.harness
```

## Optional filters

```powershell
$env:PRISM_STRESS_LIMIT="3"                                          # first N cases (smoke)
$env:PRISM_STRESS_CATEGORIES="1_numeric_boundary,7_adversarial"      # category filter
$env:PRISM_STRESS_BASE="http://127.0.0.1:8000"
```

## Outputs

- `eval/results/stress/run_<timestamp>/report.md` + per-case JSON (gitignored)
- `eval/results/stress/LATEST_REPORT.md` — latest summary (committed for verification)

Question bank: `question_bank.py` · scorers: `scorers.py` · client: `client.py`
