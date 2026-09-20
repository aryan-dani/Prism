# Prism — Jury Presentation Deck (10 slides)

**Kohler Unified Enterprise AI Agent · Track 3 · Kohler-MITWPU AI Research Lab**

Source of truth for the landscape PDF. Build with:

```powershell
# Uses system Playwright + installed Chrome (or: playwright install chromium)
python scripts/export_deck.py
# Also works if Chromium is installed for the backend venv:
# uv run --project backend python scripts/export_deck.py
```

Output: [`docs/pdf/deck.pdf`](pdf/deck.pdf) · HTML preview: [`docs/assets/deck.html`](assets/deck.html)

---

## Slide 1 — Title

**Prism — one query, any format**

- Kohler Unified Enterprise AI Agent · Track 3
- One conversational agent · five enterprise domains · any output format · fully local
- Image: `docs/assets/screenshot_landing.png`

---

## Slide 2 — Approach

**Core approach**

- One agent across **HR · Finance · Customer Support · Privacy · Legal**, plus a **session-scoped 6th domain** (your uploaded file)
- **3 real / 2 synthetic** knowledge sources — real public Kohler Assist / Privacy / Legal; synthetic Meridian Fixtures HR & Finance (**disclosed**)
- Local-first: Ollama on-device, no cloud LLM; uploads never leave the laptop
- Aligns with Kohler **design excellence** and **operational efficiency**: one front door, less tool sprawl, grounded answers

---

## Slide 3 — Architecture

**System architecture**

- React + Vite UI → FastAPI (`:8000`) with Bearer login → hand-rolled agent state machine
- Enterprise KB: embedded Chroma collection `prism_kb` + BM25 sidecar
- Ad-hoc docs: separate collection `prism_uploads` filtered by `session_id`
- RBAC: Chroma `role_*` metadata ANDed into every retrieve — not a UI-only gate
- Image: `docs/assets/diagram_architecture.png`

---

## Slide 4 — One turn

**Turn pipeline (ordered gates)**

1. Jailbreak / CFO-override refuse (no LLM)
2. Deterministic `policy_math` (leave arithmetic, INR approval bands)
3. Pure reformat of `last_answer` → five renderers, **no re-retrieval**
4. Session upload gate → `prism_uploads`
5. Non-LLM domain router (anchors + hit votes)
6. Hybrid retrieve (Chroma dense + BM25 → RRF) with role ACL
7. One `CanonicalAnswer` JSON call → prose / JSON / XML / Excel / email
- Images: `docs/assets/diagram_routing.png`, `docs/assets/diagram_canonical_fanout.png`

---

## Slide 5 — Tech stack · 8GB VRAM

**Stack sized for RTX 5070 Laptop (~8GB)**

| Layer | Choice |
|---|---|
| Generation | `qwen2.5:7b-instruct` Q4 via Ollama |
| Embeddings | `nomic-embed-text` |
| Titles | `qwen2.5:3b-instruct` (unload after use) |
| Vector store | Embedded Chroma + BM25; uploads in `prism_uploads` |
| Agent | Hand-rolled Python state machine (no LangGraph) |
| API / UI | FastAPI · React + Vite · login + format bar + voice |

Bench (12 golden Qs): **6.4s** avg · **5143 MB** peak · best Finance exactness vs Qwen3 / Llama / Mistral candidates.

---

## Slide 6 — Knowledge bases

**Five domains · one collection**

| Domain | Nature | Source |
|---|---|---|
| Customer Support | Real | assist.kohler.com scrape |
| Privacy | Real | Kohler Privacy Policy |
| Legal | Real | T&C, Prop 65, warranties, SDS |
| HR | Synthetic | Meridian Fixtures policy + staff records |
| Finance | Synthetic | Meridian guidelines + compensation |

- ~**519** chunks after index rebuild (policies + records + warranty PDF fixture)
- HR/Finance are synthetic because **no real internal Kohler manuals are public** — intentional, disclosed

---

## Slide 7 — RBAC · source authority

**Role-gated retrieval + conflict rule**

| Role | Sees |
|---|---|
| Customer | Support, Privacy, Legal only |
| General employee | + HR/Finance **policy** |
| HR staff | + named employee leave records |
| Finance staff | + CTC / compensation |

- ACL is a Chroma `where` clause (`role_{role}=True`) before any chunk reaches the LLM
- Denials logged; chat claims of authority never change role
- Conflicting sources: official PDF (`source_priority=100`) beats scraped HTML (10) — one answer + footnote, not a dump of two manuals

---

## Slide 8 — Innovation

**What makes Prism more than a chatbot**

- **Bring your own document** — PDF/DOCX/TXT mid-chat; purged on delete / 24h TTL
- **CanonicalAnswer → five formats** — reformats cost zero LLM calls
- **EPA water-conservation callout** — labeled liters/day on leak/drip Support answers
- **Voice** — browser mic + speak (Chrome/Edge)
- **Cited sources + workflow ids** — every reply points at retrieved URLs and `docs/prompts.md`
- Images: `docs/assets/screenshot_upload.png`, `docs/assets/screenshot_format_json.png`, `docs/assets/screenshot_chat.png`

---

## Slide 9 — Evidence

**Eval that backs the claims**

- Domain routing **92.1%** · retrieval hit@5 **100%**
- Adversarial stress harness: **39 / 39 PASS** (numeric bands, multi-hop, domain switch, clarification, jailbreak, honesty, formats)
- RBAC smoke: customer deny / employee policy / HR leave balance / Finance CTC / warranty PDF path — **PASS**
- Live clone-and-run: login as `alex.employee@prism.local` / `Prism2026!`

---

## Slide 10 — Shipped · ask

**Ready for the jury**

- Clone → `scripts/setup.ps1` → rebuild index → `.\start.ps1` → http://localhost:5173
- Full docs: architecture · prompts · decisions · demo script (PDFs under `docs/pdf/`)
- **Ask:** Prism as the internal + external knowledge front door — five domains, one upload, any format, on-device, role-aware

Built by **Aryan Dani** · [aryandani.com](https://www.aryandani.com)
