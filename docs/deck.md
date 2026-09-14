# Prism — Presentation Deck (max 4 slides)

Copy each slide into PowerPoint / Google Slides / Canva. Keep to **four slides**. Export PDF for the repo.

---

## Slide 1 — Approach & Pitch

**Title:** Prism — One query, any format  
**Subtitle:** Kohler Unified Enterprise AI Agent · Track 3

- One conversational agent across **five domains**: HR · Finance · Customer Support · Privacy · Legal/Compliance
- **3 real / 2 synthetic** knowledge sources — real public Kohler Support/Privacy/Legal; synthetic Meridian Fixtures HR & Finance (disclosed) because no internal manuals are public
- Innovation beats: **non-LLM domain routing**, **canonical answer object** with five renderers, **honest no-answer** for Legal/Privacy
- Aligns with Kohler design excellence & operational efficiency: one agent, less tool sprawl, grounded answers, local-first (data stays on-device)

---

## Slide 2 — System Architecture

**Title:** Architecture

```
User → FastAPI + React UI
         ↓
   Intent detect (reformat? clarify reply?)
         ↓
   Domain router (embedding anchors + hit votes)  ← no LLM
         ↓
   Hybrid retrieve (Chroma dense + BM25 → RRF)
         ↓
   One CanonicalAnswer (single local LLM call)
         ↓
   Renderers: prose | JSON | XML | Excel | email
```

- Multi-turn `SessionState`: history, last docs, last answer, pending clarification
- Domain switch + anaphora without restarting the session

---

## Slide 3 — Tech Stack (8GB VRAM budget)

**Title:** Stack · sized for RTX 5070 8GB

| Layer | Choice |
|---|---|
| Generation | Q4 7–8B via Ollama (benchmarked; see decisions.md) |
| Embeddings | `nomic-embed-text` (tiny / shared budget) |
| Vector store | Embedded Chroma + BM25 sidecar · one tagged collection |
| Agent | Hand-rolled Python state machine |
| API / UI | FastAPI · React + Vite |
| Ingest | `__NEXT_DATA__` parse for Assist; `curl_cffi` for kohler.com |

Constraint-driven: no multi-LLM routing, no separate vector DB server, reformats cost $0 LLM.

---

## Slide 4 — Innovation & Impact

**Title:** Why this wins the evaluation criteria

- **Approach (45%):** Canonical answer + renderer split; embedding-router instead of an LLM classifier; clarification & no-answer honesty
- **Execution (25%):** Full Assist scrape (~330 unique articles), validated samples/domain, hybrid retrieval, local reproducible index
- **UX (20%):** Session sidebar, auto-titles, format bar, Excel download, source citations
- **Business (10%):** Fewer handoffs between HR/Finance/Support/Legal tools; grounded compliance answers; water/product support knowledge retained from real Assist content

**Ask:** Deploy Prism as the internal+external knowledge front door — one chat, five domains, any output format.
