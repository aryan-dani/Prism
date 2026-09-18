# Prism — System Architecture

This document is the map of the repository: what Prism does, where each of the
five knowledge bases comes from, how a chat turn runs, and how we plan to
improve the system. Decision *rationale* (why Chroma, why Qwen, VRAM math)
lives in [`decisions.md`](decisions.md). Prompt / non-LLM workflow inventory
lives in [`prompts.md`](prompts.md).

---

## 1. What Prism is

A **local-first RAG agent** for the Kohler–MITWPU Track 3 case study:

- One conversational agent over **five domains**: HR, Finance, Customer Support, Privacy, Legal
- One structured **`CanonicalAnswer`** per turn → re-render as prose / JSON / XML / Excel / email without re-asking the LLM
- **Ollama** for embeddings + generation (no cloud LLM)
- **Hand-rolled** Python turn control (`prism/core/agent.py`) — not LangGraph / LangChain agent loops

Target hardware: ~8GB NVIDIA VRAM (developed on RTX 5070 Laptop).

```
┌─────────────────┐   HTTP :8000    ┌──────────────────────────────┐
│  frontend/      │◄───────────────►│  backend/prism/api (FastAPI) │
│  React + Vite   │                 └──────────────┬───────────────┘
└─────────────────┘                                │
                                     ┌─────────────▼─────────────┐
                                     │  core/agent.py            │
                                     │  turn state machine       │
                                     └───┬──────────┬────────┬───┘
                     SessionStore        │          │        │
                     SQLite              ▼          ▼        ▼
                     data/sessions.db   Router   Retriever  answer.py
                                        +anchors Chroma+BM25 Ollama gen
                                                 data/chroma/
```

| Layer | Role | Path |
|---|---|---|
| UI | Sessions, chat, format bar, Excel download | `frontend/` |
| API | Sync chat, render, download | `backend/prism/api/` |
| Agent | Ordered gates + RAG orchestration | `backend/prism/core/agent.py` |
| Index | One collection `prism_kb` + BM25 sidecar | `backend/data/chroma/` |
| LLM | Gen / embed / titles | Ollama (`OLLAMA_HOST`) |

---

## 2. The five knowledge bases

All domains land in **one** Chroma collection with `domain` metadata and boolean
`domain_<name>` flags (so cross-tagged chunks, e.g. warranty = legal + CS, are
filterable). Counts are approximate; rebuild reports the exact total (~497).

| Domain | Nature | Source | Processed JSONL | ~Chunks |
|---|---|---|---|---|
| **Customer Support** | Real | Crawl [`assist.kohler.com`](https://assist.kohler.com) → `data/raw/assist/` | `processed/customer_support.jsonl` | ~331 |
| **Privacy** | Real | kohler.com Privacy Policy (rendered HTML cache under `raw/kohler_legal/`) | `processed/privacy.jsonl` | ~51 |
| **Legal** | Real | Assist warranties / Prop 65 / SDS / green-building **+** kohler.com Terms | `legal_from_assist.jsonl` + `legal_from_kohler.jsonl` | ~45 |
| **HR** | Synthetic | Authored `data/synthetic/hr_policy.md` (Meridian Fixtures Inc.) | `processed/hr.jsonl` | ~49 |
| **Finance** | Synthetic | Authored `data/synthetic/finance_policy.md` | `processed/finance.jsonl` | ~22 |

### Ingest pipeline

1. **`prism.ingest.crawl_assist`** — sitemap → polite fetch (~1 req/s) → parse `__NEXT_DATA__` `displayCard` → classify CS vs legal cross-tags  
2. **`prism.ingest.parse_kohler_legal`** — heading-boundary HTML chunks for privacy / T&C  
3. **`prism.ingest.build_synthetic`** — HR / Finance markdown → JSONL  
4. **`prism.ingest.build_index`** — merge all `processed/*.jsonl` → embed (`nomic-embed-text`) → rebuild Chroma + BM25 pickle  

```powershell
cd backend
uv run python -m prism.ingest.build_index
```

| Path | Committed? | Notes |
|---|---|---|
| `data/synthetic/*.md` | Yes | Student-authored policies |
| `data/processed/*.jsonl` | Yes | Rebuild input |
| `data/raw/` | No (gitignored) | Crawl / HTML caches |
| `data/chroma/` | No | Local index + `_embed_cache.jsonl` + `bm25_index.pkl` |
| `data/sessions.db` | No | Chat state |

---

## 3. Runtime: one chat turn

`POST /api/sessions/{id}/chat` → `handle_turn` → persist session → `ChatResponse`.

Gates run **in order**. Early returns skip the LLM when possible (safety + exact math).

| Step | What | Module |
|---|---|---|
| 0a | Jailbreak / prompt-exfil refuse | `text_utils` → `agent` |
| 0b | CFO / fake policy-override refuse | `text_utils` → `agent` |
| 0c | Deterministic leave / termination math | `policy_math` |
| 1 | Pure reformat of `last_answer` (JSON/XML/Excel/email) | `agent` + `renderers/` |
| 2 | Resolve clarification; vague cold-start clarify | `agent` |
| 2c | “What did I ask N questions ago?” from history | `agent` |
| 2d | **Uploaded-doc gate** — if the session has attachments and the user points at them (or upload retrieval is confident vs. the KBs), answer from the session-scoped `prism_uploads` collection | `agent` + `uploads` |
| 3 | Anaphora expansion (+ one small “focus” retrieval on the raw follow-up); long-range CL carry-forward email recall | `agent` |
| 4 | Route (embed + hit votes + anchors; sticky domain; ambiguity → ask) | `router` |
| 5 | Hybrid retrieve (dense + BM25 → RRF); multi-domain merge when needed | `retriever` + `store` |
| 6 | Relevance / fused confidence → else `no_context_answer` | `retriever` |
| 7 | One Ollama JSON generation → `CanonicalAnswer` (+ one repair) | `answer` |
| 8 | Polish (yes/no-only, anti-sycophancy, dedupe) | `answer_polish` |
| 9 | Render prose (or email); store `last_answer` / sources | `renderers` + `memory` |

**Formats later:** `POST …/render` or chat-side pure reformat — both operate on the stored canonical object (no second retrieval).

### Retrieval details

- **Dense:** Chroma cosine over `nomic-embed-text` vectors  
- **Sparse:** BM25 over tokenized text; sidecar stores **ids + docs + metadatas** (no per-hit Chroma `get`)  
- **Fusion:** Reciprocal rank fusion (`RRF_K=60`)  
- **Confidence:** dense distance under domain floor **or** strong BM25 rank / dual-signal fused score (so exact ₹ / model tokens aren’t false “no answer”)  
- **Multi-domain:** per-domain `top_k=3` (≤4 domains), fuse ≤6; **skip agnostic pass** when ≥2 domain signals (or one signal with confident hits)  

### Deterministic guards (no LLM)

Documented also in `prompts.md` §4: jailbreak, CFO override, CL carry / leave-year math, yes/no-only collapse, session lookback, long-range carry-forward email, leading-number correction, fake-model refuse.

---

## 4. Key modules

| Path | Role |
|---|---|
| `prism/api/routes.py` | Health (incl. Ollama + upload stats), sessions, chat, render, Excel, `upload` / `uploads` |
| `prism/core/agent.py` | Turn state machine |
| `prism/core/router.py` | Domain routing without an LLM |
| `prism/core/retriever.py` | Hybrid retrieve + confidence |
| `prism/core/store.py` | Chroma + BM25 |
| `prism/core/answer.py` | `CanonicalAnswer` schema + generation |
| `prism/core/answer_polish.py` | Post-validation / constraints |
| `prism/core/policy_math.py` | Code-side leave arithmetic |
| `prism/core/memory.py` | Session state + SQLite (incl. `uploaded_docs` refs) |
| `prism/core/uploads.py` | Session-scoped upload store: parse → chunk → embed → `prism_uploads` collection; per-session BM25; TTL purge |
| `prism/core/text_utils.py` | Heuristics (jailbreak, multi-domain, formats) |
| `prism/core/renderers/*` | Prose / JSON / XML / Excel / email |
| `prism/ingest/*` | Crawl, parse, chunk, index |
| `eval/stress/*` | Live API adversarial harness |

---

## 5. Eval & stress

- **`eval/stress/harness.py`** — black-box multi-turn cases against `:8000`  
- Bank: `eval/stress/question_bank.py`  
- Latest rollup: `backend/eval/results/stress/LATEST_REPORT.md`  
- Must run **sequentially** on 8GB VRAM  

Companion: `eval/run_eval.py`, `eval/bench_models.py`, `prism.ingest.validate`.

---

## 6. Configuration

| Env var | Default | Purpose |
|---|---|---|
| `PRISM_GEN_MODEL` | `qwen2.5:7b-instruct` | Answer generation |
| `PRISM_EMBED_MODEL` | `nomic-embed-text` | Embeddings / routing |
| `PRISM_TITLE_MODEL` | `qwen2.5:3b-instruct` | Session titles |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama |
| `PRISM_UPLOAD_MAX_BYTES` | `12 MB` | Max upload size |
| `PRISM_UPLOAD_TTL_HOURS` | `24` | Purge uploaded vectors/files older than this (checked at startup) |
| `PRISM_UPLOAD_KB_MARGIN` | `0.06` | Implicit questions route to the upload only if within this dense-distance margin of the KB's best hit |

Health: `GET /api/health` → `status`, `chunks_indexed`, configured models, `ollama.{reachable,models_missing,ok}`, and `uploads.{chunks_indexed,ttl_hours,max_bytes,allowed_suffixes}`.

---

## 7. Improvement roadmap

Ordered by impact × effort given **current** code (not generic RAG advice).

### P0 — shipped

1. **Cache BM25 metadatas** in `bm25_index.pkl` — eliminate per-hit Chroma `get`  
2. **Cap multi-domain cost** — skip agnostic retrieve when domain signals are clear  
3. **Fused / lexical confidence** — dense floor **or** strong BM25 / dual RRF  
4. **Health checks Ollama + models** — `degraded` when unreachable or models missing  

### P1 — shipped

5. **Deterministic Finance approval-band lookup** — claim amount → Section 2.1 band in `policy_math`  
6. **SSE status streaming** — `POST …/chat/stream` emits stage events; final `result` is full ChatResponse (no partial JSON)  
7. **Bypass-paraphrase stress** — `adv_06` / `adv_07` hit LLM+polish path (not regex short-circuits)  
8. **Sticky→switch regression** — `switch_03` HR leave then faucet → `customer_support`; `switch_01` requires ≥2 domains  

### P2 / P3 — shipped

9. **UI states** — clarification / no-answer banners + confidence chips; turn metadata persisted  
10. **`scripts/rebuild_index.ps1`** — fails loudly if required domain JSONL missing/empty  
11. **Ollama keep-alive** — `PRISM_OLLAMA_KEEP_ALIVE` (default `25m`) + startup warm  
12. **Citation ⊆ retrieved URLs** — polish drops sources not in retrieved chunks  
13. **Multi-user session store** — SQLite WAL + RLock + busy timeout around session CRUD  

### Final sprint — shipped

14. **Session-scoped document upload (ad-hoc 6th domain)** — `POST …/upload`; PDF / DOCX / TXT / MD / CSV / JSON / HTML; separate `prism_uploads` collection filtered by `session_id`; dense + comparative-vs-KB confidence gate; purged on delete / remove / 24h TTL. Frontend: attach button, drag-and-drop, active-doc chips. See `decisions.md` §10.  
15. **Anaphora focus retrieval** — extra `top_k=3` pass on the raw follow-up so topic pivots (“covered under warranty?”, “refund instead?”) surface the right chunks. See `decisions.md` §11.  

Track progress against this list in PRs; update this section when an item ships.

---

## 8. Related docs

| Doc | Contents |
|---|---|
| [`decisions.md`](decisions.md) | Why each infra/model choice |
| [`prompts.md`](prompts.md) | Prompts + non-LLM workflows |
| [`demo_script.md`](demo_script.md) | Demo narrative |
| [`deck.md`](deck.md) | Slide outline |
| [`../backend/eval/stress/README.md`](../backend/eval/stress/README.md) | How to run stress |
