# Prism

**Kohler Unified Enterprise AI Agent** · Track 3 · Kohler-MITWPU AI Research Lab

> One query, any format — a local conversational agent that reasons across five enterprise knowledge domains and re-renders the same answer as prose, JSON, XML, Excel, or a draft email.

Built for the Kohler-MITWPU AI Research Lab case study challenge (individual submission). Runs fully offline via [Ollama](https://ollama.com/) on a laptop with an RTX 5070 (8GB VRAM).

![Prism landing page — five domains plus your uploaded file, how-it-works, curated example questions](docs/assets/screenshot_landing.png)

![Prism chat — exact ₹25,001 vs ₹24,999 approval-band boundary, with domain chip, confidence, sources, and format bar](docs/assets/screenshot_chat.png)

---

## What it does

| Capability | How |
|---|---|
| **Five domains, one agent** | HR · Finance · Customer Support · Privacy · Legal/Compliance |
| **Multi-turn reasoning** | Session memory, anaphora (“that one…”), mid-conversation domain switching |
| **Clarification-seeking** | Asks a short question when domain routing is ambiguous — doesn’t guess |
| **Honest no-answer** | Refuses to fabricate when retrieval isn’t confident (stricter for Legal/Privacy) |
| **Dynamic output formats** | One canonical answer object → prose / JSON / XML / Excel / email without re-retrieval |
| **Bring your own document** | Drop a PDF / DOCX / TXT / CSV into the chat → indexed locally as a session-scoped sixth domain, answerable immediately alongside the five KBs; purged when the chat is deleted (24h TTL) |
| **Role-based access (RBAC)** | Login with demo roles (customer → HR/Finance staff). Retrieval filters by Chroma `role_*` metadata before any chunk reaches the LLM |
| **Voice** | Browser Web Speech — mic dictation + speak-answer (Chrome/Edge); no cloud STT |
| **Cited sources & prompts** | Every answer lists retrieved sources; UI labels the workflow id documented in [`docs/prompts.md`](docs/prompts.md) |
| **Local-first** | Ollama + embedded Chroma; no cloud LLM, no separate vector DB server — uploaded documents never leave the machine |

**Architecture map:** [`docs/architecture.md`](docs/architecture.md) — system diagram, five knowledge bases (sources + ingest), turn pipeline, module index, improvement roadmap.  
**Decision log:** [`docs/decisions.md`](docs/decisions.md) · **Prompts / workflows:** [`docs/prompts.md`](docs/prompts.md)

### Prompts & citations (jury)

Judges ask for the prompts and sources behind answers. Prism surfaces both:

1. **Full prompt inventory** — [`docs/prompts.md`](docs/prompts.md) (PDF: [`docs/pdf/prompts.pdf`](docs/pdf/prompts.pdf)): system prompt (`prism/core/answer.py` → `SYSTEM_PROMPT`), titler prompts, and every non-LLM workflow (`policy_math`, RBAC deny, reformat, clarify, upload RAG, …).
2. **In the chat UI** — each assistant reply shows **Sources** (domain + title/URL from retrieved chunks) and a **Prompt / workflow** line with the workflow id that answered the turn (e.g. `rag_canonical`, `policy_math`, `rbac_deny`). Citation integrity drops model-claimed URLs that were not retrieved.

---

## Quick start

### Prerequisites

- Windows 10/11 with ~8GB NVIDIA VRAM (developed on RTX 5070 Laptop)
- [Ollama](https://ollama.com/) installed and running
- Python **3.11+** and [uv](https://github.com/astral-sh/uv)
- Node.js **20+**

### 1. Install

```powershell
# One-shot (Python deps in backend/ + Ollama models + frontend deps)
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
```

Or manually:

```powershell
cd backend
uv sync
cd ..

ollama pull nomic-embed-text
ollama pull qwen2.5:7b-instruct      # generation (default after bench)
ollama pull qwen2.5:3b-instruct      # session titles only
# optional candidates: qwen3:8b, llama3.1:8b-instruct-q4_K_M, mistral:7b-instruct
# or: powershell -File scripts/pull_models.ps1

cd frontend
npm install
cd ..
```

### 2. Build the vector index

Processed JSONL for all five domains is in `backend/data/processed/`. Build (or rebuild) the local Chroma + BM25 index:

```powershell
cd backend
uv run python -m prism.ingest.build_index
cd ..
```

Or from the repo root (fails loudly if any domain JSONL is missing/empty):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/rebuild_index.ps1
```

Expected: **~519 chunks** indexed into collection `prism_kb` (includes HR records, compensation, warranty PDF fixture).

### 2. Run

Launch both Backend API and Frontend UI:

```powershell
.\start.ps1
# Linux/macOS: bash scripts/start.sh
```

Open **http://localhost:5173**. Sign in with a demo account (printed on the login card).

**Smoke-test login (full domain access):** `alex.employee@prism.local` / `Prism2026!`

| Role | Example email | Sees |
|---|---|---|
| Customer | `priya.customer@prism.local` | Support, Privacy, Legal only |
| General Employee | `alex.employee@prism.local` | + HR/Finance policies |
| HR Staff | `riya.hr@prism.local` | + employee leave records |
| Finance Staff | `arun.finance@prism.local` | + CTC / compensation |

Shared password for all seeded users: **`Prism2026!`**

API docs: http://127.0.0.1:8000/docs · Health (no auth): http://127.0.0.1:8000/api/health

**Runtime KB upsert (bonus):**

```powershell
cd backend
uv run python -m prism.ingest.upsert --file eval/fixtures/k_3901_warranty.pdf --domain legal --source-id fixture-k3901-warranty --replace-source
```

---

## Tech stack (8GB VRAM budget)

| Layer | Choice | Why |
|---|---|---|
| **Generation** | `qwen2.5:7b-instruct` (Q4) | Best Finance exactness + lowest latency in local bench |
| **Embeddings** | `nomic-embed-text` (~274MB) | Tiny footprint so the 7B model keeps most of VRAM |
| **Titles** | `qwen2.5:3b-instruct` | Cheap one-shot session naming |
| **Vector store** | Embedded Chroma + BM25 sidecar | No separate server; one tagged collection for all domains |
| **Routing** | Embedding anchors + hit votes | **No LLM call** just to pick a domain |
| **Agent** | Hand-rolled Python state machine | Explicit, debuggable — no LangGraph/LlamaIndex overhead |
| **API / UI** | FastAPI · React + Vite + TypeScript | Session sidebar, format bar, Excel download |

Full decision log (model bench table, scrape strategy, 3-real/2-synthetic sourcing): [`docs/decisions.md`](docs/decisions.md) · PDF: [`docs/pdf/decisions.pdf`](docs/pdf/decisions.pdf)

### Model benchmark (12 golden questions, RTX 5070 8GB)

| Model | Schema OK | Fact Recall | Finance Exactness | Avg Latency | Peak VRAM |
|---|---|---|---|---|---|
| **qwen2.5:7b-instruct** ★ | 100% | **74%** | **67%** | **6.4s** | **5143 MB** |
| qwen3:8b | 100% | 74% | 67% | 18.4s | 6241 MB |
| llama3.1:8b-instruct-q4_K_M | 100% | 74% | 33% | 9.9s | 6022 MB |
| mistral:7b-instruct | 100% | 78% | 33% | 15.4s | 5726 MB |

Qwen3 matches quality on this slice but is ~3× slower and uses more VRAM — default stays Qwen2.5. Override anytime: `$env:PRISM_GEN_MODEL="qwen3:8b"`

Routing-only eval (40 questions): **92.1%** domain accuracy · **100%** hit@5 · ~76ms avg

**Adversarial stress harness (39 cases, 13 categories):** **39 PASS · 0 PARTIAL · 0 FAIL · 0 NEEDS_HUMAN_REVIEW** — see [`backend/eval/results/stress/LATEST_REPORT.md`](backend/eval/results/stress/LATEST_REPORT.md). Covers numeric-boundary exactness, cross-domain multi-hop, silent domain switching, ambiguity/clarification, 12-turn memory, hallucination/honesty probes, jailbreak/prompt-injection/policy-tamper adversarial cases (including paraphrased variants), output-format consistency, cross-session consistency, citation-domain integrity, session UX, and a 20-turn latency/perf sweep.

---

## Knowledge domains

| Domain | Source | Notes |
|---|---|---|
| **Customer Support** | Real — full scrape of [assist.kohler.com](https://assist.kohler.com/en/sitemap) | ~331 unique articles; `__NEXT_DATA__` parse (no nav/footer noise) |
| **Privacy** | Real — Kohler Privacy Policy | Heading-boundary chunks; CCPA cookies URL currently 404 (flagged, not synthesized) |
| **Legal / Compliance** | Real — T&C, Prop 65, SDS, green-building, warranties | Warranty pages cross-tagged with Customer Support |
| **HR** | Synthetic — Meridian Fixtures HR Policy | Disclosed; structure informed by reference `BU_HR_Manual_.pdf` |
| **Finance** | Synthetic — Meridian Fixtures Finance Policy | Disclosed; deliberate ₹ approval bands for exactness demos |

HR/Finance are synthetic because no real internal Kohler manuals are public. That split is intentional and documented — not “whatever was easiest.”

### Known limitations

- Expense **approval bands are by claim amount, not grade**. “If I get promoted, what’s my new expense limit?” is still the same ₹5k / ₹25k / ₹1L table unless the user also states a rupee amount.
- **Upload vs KB**: implicit questions only go to an attached file when the file is a closer dense match than the five KBs. Say “this document…” (or the filename) to force the upload path.
- **Latency scales with GPU contention.** On an 8GB laptop GPU, all three Ollama models (7B generation + 3B titler + embedder) plus whatever else is drawing VRAM (this repo was built inside Cursor, which itself competes for the same GPU) leave little headroom for the KV cache on longer, multi-turn conversations — single-turn latency measured 2-15s with the GPU free vs. 40-90s under real contention on this dev box. The title model now unloads immediately after each use (`OLLAMA_TITLE_KEEP_ALIVE=0`) to claw back ~2GB, and a bounded request timeout (`PRISM_OLLAMA_TIMEOUT_S`) turns a genuine stall into an honest "please retry" instead of a hung request — but for a live demo, close other GPU-heavy apps first.
- **Privacy KB spans multiple jurisdictions** (US state law, Canada/PIPEDA, Brazil/LGPD, EU) with very similar boilerplate "your rights" language — dense retrieval alone can land two countries within ~0.02 cosine distance of each other. Prism filters out chunks from a *different* named jurisdiction once the query clearly states one (see `filter_cross_jurisdiction_chunks`), but the literal acronym "CCPA" never appears on Kohler's real public privacy page — California rights are described under "Shine the Light" / state-privacy-rights language instead, so an eval expecting that exact acronym will legitimately miss even though the underlying rights are covered.
- Customer Support / Privacy / Legal are **public Kohler pages**, not internal ticketing or employee PII stores.

---

## Architecture

```
User message
    │
    ├─ jailbreak / CFO-override? ──► deterministic refuse (no LLM)
    ├─ leave arithmetic pattern? ──► code-computed answer (policy_math)
    ├─ reformat request? ──► render(last_answer)     # no retrieval, no LLM
    ├─ clarify reply? ─────► force chosen domain
    ▼
Domain router (embedding anchors + hit votes)
    │ ambiguous? ──► ask clarifying question
    ▼
Hybrid retrieve (Chroma dense + BM25 → RRF; per-domain merge for multi-hop)
    │ low relevance? ──► honest no-answer
    ▼
One CanonicalAnswer (single Ollama JSON call)
    ▼
Renderers: prose | JSON | XML | Excel | email
```

---

## Project layout

```
Prism/
├── frontend/            # React + TypeScript + Vite chat UI
│   ├── src/             # App, API client, styles
│   └── package.json
├── backend/             # FastAPI + Ollama + RAG agent
│   ├── prism/           # api/, core/, ingest/
│   ├── data/            # processed/ (commit), synthetic/, chroma/ (local), raw/ (local)
│   ├── eval/            # golden set, model bench, stress harness + LATEST_REPORT
│   ├── pyproject.toml
│   └── uv.lock
├── references/          # Non-ingested structural refs (HR templates, AFOA finance PDF)
├── docs/                # decisions, prompts, deck, demo script + pdf/ + assets/ (screenshots)
├── scripts/             # setup.ps1, start.ps1, pull_models.ps1, export_pdfs.py
├── start.ps1            # thin wrapper → scripts/start.ps1
└── README.md
```

---

## Evaluation & validation

```powershell
cd backend

# Model comparison (optional limit for a faster pass)
$env:PRISM_BENCH_LIMIT="12"
uv run python -m eval.bench_models

# Routing + multi-turn behaviors
uv run python -m eval.run_eval

# Hand-review samples (20 random chunks / domain)
uv run python -m prism.ingest.validate

# Adversarial stress harness (sequential; API must already be on :8000)
# Smoke: $env:PRISM_STRESS_LIMIT="3"
uv run python -m eval.stress.harness
# → backend/eval/results/stress/LATEST_REPORT.md

# RBAC + conflict smoke (login as customer / employee / HR / finance)
uv run python -m eval.stress.rbac_smoke

cd ..
```

Validation reports: [`backend/eval/results/validation_summary.md`](backend/eval/results/validation_summary.md) · Stress harness: [`backend/eval/stress/README.md`](backend/eval/stress/README.md)

---

## Submission deliverables

| Requirement | Location |
|---|---|
| Working prototype | This repo — see Quick start |
| Architecture overview | [`docs/architecture.md`](docs/architecture.md) |
| Prompts documentation (PDF) | [`docs/pdf/prompts.pdf`](docs/pdf/prompts.pdf) · source [`docs/prompts.md`](docs/prompts.md) |
| Presentation deck (≤4 slides) | Outline [`docs/deck.md`](docs/deck.md) · PDF [`docs/pdf/deck.pdf`](docs/pdf/deck.pdf) |
| Demo video (1–3 min) | Script: [`docs/demo_script.md`](docs/demo_script.md) — *add link here after upload* |
| Architecture decisions | [`docs/decisions.md`](docs/decisions.md) · [`docs/pdf/decisions.pdf`](docs/pdf/decisions.pdf) |

Regenerate PDFs after doc edits:

```powershell
uv run --project backend python scripts/export_pdfs.py
```

### Demo video

> **TODO:** paste unlisted YouTube / Drive link after recording.

Suggested flow (from `docs/demo_script.md`): Finance ₹15,000 approval exactness → domain-switch to toilet troubleshooting → anaphora follow-up → clarification moment → Prose → JSON → XML → Excel → Email from one answer.

---

## Re-crawling (optional)

Polite, cached, ~1 req/sec. Respects `assist.kohler.com/robots.txt`.

```powershell
cd backend
uv run python -m prism.ingest.crawl_assist
uv run python -m prism.ingest.parse_kohler_legal
uv run python -m prism.ingest.build_synthetic
uv run python -m prism.ingest.build_index
uv run python -m prism.ingest.validate
cd ..
```

Academic use only — read-only crawl for this case study; do not republish the scraped corpus outside the project deliverable.

---

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `PRISM_GEN_MODEL` | `qwen2.5:7b-instruct` | Answer generation |
| `PRISM_EMBED_MODEL` | `nomic-embed-text` | Embeddings / routing |
| `PRISM_TITLE_MODEL` | `qwen2.5:3b-instruct` | Session titles |
| `PRISM_OLLAMA_KEEP_ALIVE` | `25m` | Keep the 7B/embed models warm between turns (`-1` = forever) |
| `PRISM_OLLAMA_TITLE_KEEP_ALIVE` | `0` | Title model (3B) keep-alive — unloads immediately after each use to free VRAM for the 7B model's KV cache on tight 8GB cards |
| `PRISM_OLLAMA_TIMEOUT_S` | `150` | Hard ceiling on a single Ollama call; a stall past this returns an honest no-answer instead of hanging the request |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama endpoint |

---

## License / academic note

Submitted as an individual academic case-study prototype for the Kohler-MITWPU AI Research Lab. Kohler Assist / kohler.com content was scraped read-only under robots.txt and rate limits for this submission only — not for redistribution or commercial reuse. Synthetic HR and Finance policies are original student work, clearly disclosed as fictional.
