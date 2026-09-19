# Prism — Presentation Deck (max 4 slides)

Copy each slide into PowerPoint / Google Slides / Canva. Keep to **four slides**. Export PDF for the repo.

---

## Slide 1 — Approach & Pitch

**Title:** Prism — One query, any format  
**Subtitle:** Kohler Unified Enterprise AI Agent · Track 3

- One conversational agent across **five domains** plus a **session-scoped 6th**: HR · Finance · Customer Support · Privacy · Legal · *your uploaded file*
- **3 real / 2 synthetic** knowledge sources — real public Kohler Support/Privacy/Legal; synthetic Meridian Fixtures HR & Finance (disclosed)
- Innovation beats: **non-LLM domain routing**, **canonical answer → five renderers**, **ephemeral local uploads**, **honest no-answer**
- Aligns with Kohler design excellence & operational efficiency: one agent, less tool sprawl, grounded answers, data stays on-device

---

## Slide 2 — Five-domain RAG core

**Title:** Architecture · eval

```
User → FastAPI + React
         ↓  guards (jailbreak, policy math)
         ↓  uploaded-doc gate (session Chroma, never the five KBs)
         ↓  Domain router (anchors + hit votes)  ← no LLM
         ↓  Hybrid retrieve (Chroma + BM25 → RRF)
         ↓  One CanonicalAnswer (qwen2.5:7b local)
         ↓  Renderers: prose | JSON | XML | Excel | email
```

- Routing **92.1%** · Hit@5 **100%** · stress harness 39 black-box cases
- Multi-turn session: sticky domain, anaphora + focus retrieval, clarification

---

## Slide 3 — What's novel here

**Title:** Ad-hoc documents + water conservation (the 45% / 10%)

- **Bring your own document.** PDF / DOCX / TXT / CSV ingested mid-chat into a *separate* Chroma collection tagged by `session_id`. Answers from the file sit beside the five KBs. Vectors and files are **purged on session delete / 24h TTL** — they never leave the laptop. That is the privacy story, not a limitation.
- **EPA water-waste callout.** Leak / drip / running-toilet Support answers get a labeled liters/day estimate from published WaterSense / Fix-a-Leak figures — same deterministic pattern as leave and ₹-band math. Kohler's sustainability line, visible on the answer, not inferred.
- Same object still re-renders as JSON / Excel / a ready-to-send email.

---

## Slide 4 — Stack · VRAM · shipped

**Title:** Stack · sized for RTX 5070 8GB

| Layer | Choice |
|---|---|
| Generation | `qwen2.5:7b-instruct` Q4 via Ollama |
| Embeddings | `nomic-embed-text` |
| Vector store | Embedded Chroma `prism_kb` + BM25; uploads in `prism_uploads` |
| Agent | Hand-rolled Python state machine |
| API / UI | FastAPI · React + Vite · landing + format bar |

Constraint-driven: no multi-LLM routing, no cloud, reformats cost $0 LLM.

**Ask:** Prism as the internal+external knowledge front door — five domains, one upload, any format, on-device.
