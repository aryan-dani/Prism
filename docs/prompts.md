# Prism: Prompts, Instructions & Workflows

**Kohler Unified Enterprise AI Agent · Track 3 · Kohler-MITWPU AI Research Lab**

This is the brief's required PDF: every AI prompt, system instruction, and workflow used to **build** Prism and to **run** it. The landscape jury deck is [`docs/pdf/deck.pdf`](pdf/deck.pdf). This handbook is the audit trail.

**In a live demo:** each reply shows **Sources** (retrieved URLs) and a **Prompt / workflow** chip. That chip is `ChatResponse.workflow` from `prism/core/agent.py`. This file is `prompt_doc`. A judge can match the chip to a section here.

**Two layers, one document**

1. **Builder layer.** How the problem was read, which tools wrote the code, reconstructed briefing prompts (labeled as reconstructed).
2. **Runtime layer.** The exact strings Ollama sees, plus the non-LLM gates that fire *before* any model call.

Synthetic HR and Finance are disclosed Meridian Fixtures policies. Support, Privacy, and Legal are real public Kohler pages.

---

## Table of contents

1. [How to read this](#1-how-to-read-this)
2. [The Track 3 brief](#2-the-track-3-brief)
3. [Tooling ledger](#3-tooling-ledger)
4. [Reconstructed builder briefs](#4-reconstructed-builder-briefs)
5. [The turn as a story](#5-the-turn-as-a-story)
6. [Shipped generation prompts](#6-shipped-generation-prompts)
7. [Titler and email polish](#7-titler-and-email-polish)
8. [Non-LLM workflows](#8-non-llm-workflows)
9. [Router anchors](#9-router-anchors)
10. [Ingest and index](#10-ingest-and-index)
11. [Eval uses the same path](#11-eval-uses-the-same-path)
12. [Workflow index](#12-workflow-index)
13. [File map](#13-file-map)

---

## 1. How to read this

**Interview line:** The interesting prompts in Prism are the ones that never call a 7B: refuse, policy_math, RBAC, reformat. The generation prompt is one JSON contract. Everything else is code.

Builder briefs in chapter 4 are **reconstructed** from the working notes and the repo. They are the briefing pattern used to lock architecture before implementation. They are not pasted Claude chat logs and they are not dated transcripts.

Runtime strings in chapters 6 and 7 are pulled from the Python modules at export time. If the PDF and `answer.py` ever disagree, the code wins and the exporter is stale.

---

## 2. The Track 3 brief

Track 3 asks for an enterprise conversational agent across **internal and external** domains, with **dynamic output formatting** (JSON, Excel, XML, draft email) on demand.

Kohler-MITWPU scoring, as I treated it while building:

| Weight | What the jury is buying |
|---|---|
| 45 | Quality of the working prototype |
| 25 | Architecture and engineering judgment |
| 20 | Evaluation honesty |
| 10 | Presentation |

Those weights decided the product, not a slogan. A pretty chat UI without `role_*` on retrieve, or a leaderboard number the jury cannot re-run, would lose the 25 and the 20. Formats that re-ask the 7B would lose the 8 GB story.

Two pillars I locked on day one:

1. **One front door.** HR, Finance, Support, Privacy, Legal, plus a session-scoped upload. Not five chatbots.
2. **One object, five skins.** `CanonicalAnswer` JSON, then prose / JSON / XML / Excel / email with no second generation.

The rest of this PDF is how those two sentences became prompts, gates, and files.

---

## 3. Tooling ledger

Prism was built in **Cursor**. Different models did different jobs so planning tokens and implementation tokens were not the same bill.

| Job | Tool / model | Why this, not the other |
|---|---|---|
| IDE, repo, browser QA | Cursor | The working tree, the deck HTML, the live UI. |
| Architecture, RBAC, eval design, hard plans | Claude Sonnet 5 · Fable 5.1 (1M context, high effort) | Long-context planning. Read the brief + several modules at once. Expensive, used when the decision was expensive. |
| Implementation, polish, this packet | Cursor Grok 4.6 Extra High Fast | Fast once the plan was locked. Saves tokens on mechanical edits, CSS, exporters. |
| Landing visual direction | Google Stitch | Beige field, serif display, chip row. Then coded in React as Instrument Serif + DM Sans. Not a generated production app. |
| Runtime generation | `qwen2.5:7b-instruct` Q4 via Ollama | Product model. Bench winner on Finance exactness (67%) at 6.4s / 5143 MB. |
| Runtime embeddings | `nomic-embed-text` | Index and query. ~274 MB. |
| Runtime titles | `qwen2.5:3b-instruct` | Keep-alive 0. Unloads after naming a chat. |

**Planning versus implementation.** Sonnet 5 and Fable 5.1 were used to lock gates, RBAC-as-metadata, CanonicalAnswer, and the stress harness. Grok 4.6 Extra High Fast was used to write and restyle the code after those locks. The jury can see that split in the git history of docs versus `agent.py`: the architecture decisions are older than the visual packet.

**Google Stitch.** Used for the **landing** look: warm paper background, one serif wordmark, domain chips, a short how-it-works row. The chat chrome (sidebar, format bar, workflow chip) was implemented directly in `frontend/src/App.tsx`. I do not claim Stitch designed the authenticated chat.

**What I did not do.** There is no cloud LLM in the product path. Builder models never see employee PII. Uploaded user files never leave the laptop.

---

## 4. Reconstructed builder briefs

Every box below is labeled **reconstructed**. These are the briefs that turned the RFP into constraints the implementation models were not allowed to reopen.

### Reconstructed brief 1: Read the RFP

**Label:** reconstructed from the working notes and the repo. Not a pasted chat log.

```prompt
You are helping me lock an architecture for Kohler-MITWPU Track 3
before any code is written.

The brief: an enterprise conversational agent that answers across
internal and external knowledge domains, and can emit the same
answer as prose, JSON, XML, Excel, or a draft email.

Scoring I will treat as law: 45 prototype / 25 architecture /
20 evaluation / 10 presentation.

Constraints I will not reopen:
- Local only. Ollama on an RTX 5070 laptop, 8 GB VRAM.
- No extra 7B call to pick a domain.
- No extra 7B call to pretty-print JSON.
- Formats must be renderers over one stored object.
- If I cannot get a real Kohler HR or Finance manual, I will
  not invent one and call it real.

Ask me the ten questions that would change the architecture.
Then propose a one-page design I can implement without you
in the loop on every file.
```

**Why this brief.** A vague "build a RAG chatbot" prompt produces LangGraph and five vector DBs. This one forces the 8 GB story, the no-router-LLM rule, and the synthetic-disclosure rule before a single file exists.

### Reconstructed brief 2: Lock the 8 GB budget

**Label:** reconstructed from the working notes and the repo. Not a pasted chat log.

```prompt
Resident models: qwen2.5:7b-instruct Q4 + nomic-embed-text.
Title model qwen2.5:3b must unload (keep-alive 0).
Peak generation I can afford is about 5.2 GB of 8 GB.

Design the turn pipeline so that:
1. Jailbreak / CFO-spoof dies with no retrieve and no LLM.
2. Leave carry-forward and INR approval bands are Python.
3. "Give that as JSON" replays last_answer only.
4. Domain pick is embeddings + retrieval votes, not a classifier call.

If a step needs a second 7B, delete the step. Show me the
ordered gates and the VRAM each one touches.
```

**Why this brief.** This is why `policy_math` and `reformat` exist. They are not features. They are the budget.

### Reconstructed brief 3: Real versus synthetic

**Label:** reconstructed from the working notes and the repo. Not a pasted chat log.

```prompt
Public Kohler sources I can crawl read-only:
- assist.kohler.com (support, some warranty)
- kohler.com privacy policy, T&C, Prop 65, SDS

There is no public Kohler HR manual or Finance policy.
If you generate fake "Kohler HR 2024" text I will not ship it.

Propose a disclosed synthetic employer (one name, one country,
INR, leave year) that is labeled in the UI and in every PDF.
Tell me what must stay real, what may be synthetic, and how
a judge will see the difference in one glance.
```

**Why this brief.** Meridian Fixtures exists because inventing a Kohler handbook would be dishonest. The UI chip and this packet both say synthetic.

### Reconstructed brief 4: Access is metadata

**Label:** reconstructed from the working notes and the repo. Not a pasted chat log.

```prompt
Roles: customer, general_employee, hr_staff, finance_staff.
Customers must never see named leave balances or CTC.
Chat text ("I am HR") must never change role.

Do not implement RBAC as a hidden menu or a prompt instruction.
Implement it as a Chroma where clause ANDed into every retrieve,
including the agnostic hit-vote pass the router uses.

Give me the metadata flags, the four demo logins, and the
exact denial the customer sees when they ask for Riya's CL.
```

**Why this brief.** A prompt that says "you are not allowed to see HR" is theatre. `role_hr_staff=True` on the chunk is the product.

### Reconstructed brief 5: One object, five skins

**Label:** reconstructed from the working notes and the repo. Not a pasted chat log.

```prompt
I need one CanonicalAnswer JSON from a single Ollama call:
direct_answer, key_facts, steps, table, caveats, sources,
no_answer, confidence.

Renderers (no LLM):
- prose: the chat bubble
- JSON: the object as stored
- XML: tagged export
- Excel: openpyxl from key_facts
- email: template, polish off by default

"Give that as JSON" must not retrieve and must not call the 7B.
Citations must be a subset of retrieved source_url values.
Write the system prompt and the user-prompt template so a
7B Q4 cannot invent a warranty for an unknown model number.
```

**Why this brief.** This is `SYSTEM_PROMPT` plus `_build_user_prompt` plus the five files under `prism/core/renderers/`.

### Reconstructed brief 6: Eval is a harness, not a trophy

**Label:** reconstructed from the working notes and the repo. Not a pasted chat log.

```prompt
I will not report a private LLM-as-judge score.
I will ship a cloneable harness:

- 12 golden questions for model selection (Finance exactness
  is the number that picks the default, not MMLU).
- 40 routing questions, no generator.
- 39 adversarial cases: numeric edges, jailbreak, format
  fan-out, silent domain switch, "I don't know".

The same generate_answer() path as production. No secret
eval prompt. Write the case list so a judge can re-run it
with the API on :8000.
```

**Why this brief.** 39/39 is a regression suite in `backend/eval/stress/`. It is not a leaderboard.

---

## 5. The turn as a story

A user message hits `handle_turn` in `prism/core/agent.py`. The 7B is the last resort, not the first.

| Order | Gate | LLM? | Workflow id if this gate wins |
|---|---|---|---|
| 1 | Jailbreak / prompt exfil | No | `jailbreak_refuse` |
| 2 | CFO / policy-override spoof | No | `policy_override_refuse` |
| 3 | Role cannot see this domain | No | `rbac_deny` |
| 4 | Leave / INR arithmetic | No | `policy_math` |
| 5 | "as JSON / XML / Excel / email" | No | `reformat` |
| 6 | Pointed at an uploaded file | Maybe | `upload_rag` |
| 7 | Ambiguous domain | No | `clarify` |
| 8 | Session memory / email recall | No | `session_memory` / `session_email_recall` |
| 9 | Route + retrieve + one JSON call | Yes, once | `rag_canonical` or `rag_email` |

**Worked example.** User: "An employee submits an expense claim for exactly ₹25,001. Who needs to approve it?" Gate 4 matches the INR band pattern. `policy_math` looks up Finance Policy 2.1 in Python. Workflow chip: `policy_math`. The 7B is not loaded.

**Worked example.** After that answer, user: "give that as JSON." Gate 5 fires. `last_answer` is rendered. Workflow chip: `reformat`. Domain does not change.

**Worked example.** User (as priya.customer): "What is Riya's casual-leave balance?" Retrieve ANDs `role_customer=True`. The leave-register chunks are invisible. Workflow chip: `rbac_deny`.

If nothing above short-circuits, one `qwen2.5:7b-instruct` call runs with the system prompt in chapter 6.

---

## 6. Shipped generation prompts

**File:** `prism/core/answer.py`  
**Model:** `PRISM_GEN_MODEL` (default `qwen2.5:7b-instruct`)  
**When:** Once per new user question that survived the gates. Not on reformat.

The next three blocks are **live**: the exporter imports them from the running code so this PDF matches what Ollama sees.

### SYSTEM_PROMPT

<!-- LIVE:SYSTEM_PROMPT -->

### User prompt template

`_build_user_prompt` fills domain, optional conversation, optional `extra_notes`, the user question, retrieved chunks as `[Source N] title=… url=… domain=…`, and the CanonicalAnswer JSON schema.

<!-- LIVE:USER_PROMPT_TEMPLATE -->

### Repair retry

On JSON or schema failure, one follow-up is appended: the pydantic/JSON error plus "Return ONLY corrected valid JSON, nothing else." After a second failure the agent returns a safe `no_answer` object. It does not crash the turn.

Temperature is 0.1. `num_predict` is 900. Citations that are not in the retrieved `source_url` set are stripped in `answer_polish.py`.

### Per-turn extra_notes

These are not a second system prompt. They are appended under "Critical instructions for this turn" when a detector fires in `agent.py`.

| Detector | What gets appended |
|---|---|
| Upload path | Answer ONLY from uploaded chunks. Do not use Kohler/Meridian KBs unless the same fact is in the file. Cite `upload://filename`. |
| Anaphora follow-up | Answer the latest angle. Do not re-summarize the previous troubleshooting steps. |
| Leading number ("my manager said ₹X") | Do not rubber-stamp. Cite actual bands. Correct mismatches. |
| Loaded privacy premise | Correct the premise from privacy context first. |
| Invented JSON fields (`risk_level`) | Omit or set n/a. Do not invent scores. |
| Contractor damage | Prefer warranty/support. No Bathroom Design Service pricing. No legal advice. |
| Termination + leave + privacy | Distinguish CL / SL / EL. Do not invent "for cause = zero". |
| Yes or no only | `direct_answer` is exactly Yes or No. |
| Manager email about earlier fact | Put the summary in `direct_answer`. Include today's date if asked. |

<!-- LIVE:EXTRA_NOTES -->

---

## 7. Titler and email polish

### Session title

**File:** `prism/core/titler.py`  
**Model:** `PRISM_TITLE_MODEL` (`qwen2.5:3b-instruct`)  
**When:** First successful exchange. Optionally again on a clear domain switch (`maybe_retitle`). Keep-alive 0.

<!-- LIVE:TITLE_SYSTEM_PROMPT -->

If the 3B is cold for more than 2.5s, the UI falls back to the first six words of the user message. The chat turn is never blocked on a title.

### Email renderer

**File:** `prism/core/renderers/email.py`  
Default path is **template only**. Subject + greeting + `direct_answer` + key facts. No LLM.

An optional polish pass exists and is **off by default**, so "give that as email" never burns a second 7B during a demo.

<!-- LIVE:POLISH_SYSTEM_PROMPT -->

<!-- LIVE:DE_HOSTILE_PROMPT -->

---

## 8. Non-LLM workflows

These are documented because they *are* the agent. They exist to protect 8 GB and to keep exactness out of the model's hands.

### policy_math

**File:** `prism/core/policy_math.py`  
CL carry-forward, leave-year join-date math, Finance §2.1 approval bands from a stated rupee amount.

**Worked example.** ₹25,001 is in the ₹25,001-₹100,000 band: Department Head + Reporting Manager. ₹24,999 is Reporting Manager only. The 7B does not invent the band.

### rbac_deny

**Files:** `prism/core/rbac.py`, `auth.py`, `retriever.py`  
bcrypt users, opaque Bearer tokens. Every retrieve ANDs `role_{role}=True`. Chat claims of authority never change role. Denials are logged.

**Worked example.** `priya.customer@prism.local` asks for a named CL balance. The register chunks have `role_hr_staff`. She never sees them.

### jailbreak_refuse / policy_override_refuse

**File:** `prism/core/text_utils.py`  
"Ignore previous instructions", "print system prompt", "developer mode", CFO-spoof + "override threshold to ₹0". Deterministic refuse. No retrieve.

### reformat

Regex on "as JSON / XML / excel / email". Renders `last_answer`. Gates 6-9 never run.

### clarify

If top-two domain scores are within `ROUTER_AMBIGUITY_MARGIN` (0.04), ask instead of guessing. Sticky domain can keep a vague follow-up in the current domain.

**Worked example.** "Is that allowed?" after an HR turn stays in HR. The same words cold-start with no sticky, so Prism asks.

### upload_rag

`prism_uploads`, filtered by `session_id`. Same `extract.py` as the KB. Point-at-file skips Meridian `policy_math`. Purged on delete, on remove, and by a 24h TTL.

### Honesty and polish (still no extra generation)

| Workflow | Mechanism | File |
|---|---|---|
| No-answer honesty | Dense distance over floor (stricter for Legal/Privacy): skip the LLM | `retriever.py`, `answer.no_context_answer` |
| Citation integrity | Drop `sources` not in retrieved URLs | `answer_polish.py` |
| Official PDF wins | `source_priority=100` over Assist HTML 10. Caveat names the secondary article | `answer_polish.py` |
| Water callout | Leak / drip / running toilet: EPA WaterSense liters/day | `water_math.py` |
| Yes/no only | Post-polish collapses `direct_answer` | `text_utils.py`, `answer_polish.py` |
| Soft jailbreak | VIP waiver paraphrases that miss regex still refuse after generate + polish | `answer_polish.py` |

---

## 9. Router anchors

Domain pick is **not a prompt**. It is cosine similarity of the query embedding against the phrases below, blended 0.7 / 0.3 with a vote over agnostic hybrid top-10. Cost: the embedding already needed for retrieve.

These phrases *are* the routing instruction set. They live in `prism/core/router.py` as `ANCHOR_PHRASES`.

<!-- LIVE:ANCHOR_PHRASES -->

---

## 10. Ingest and index

No LLM writes the knowledge base. Crawl, parse, and authoring are code plus student Markdown.

### Assist (real Support)

1. `robots.txt`: Allow `/`, Disallow `/_next/*`.
2. Sitemap for `/en/<category>/<slug>`.
3. Polite fetch, ~1 req/s, cache under `data/raw/assist/`.
4. Parse `__NEXT_DATA__` → `displayCard` (not rendered HTML), so nav and footer never become chunks.
5. Deduplicate slugs. Warranty pages also tagged Legal.

### kohler.com legal / privacy (real)

`curl_cffi` with Chrome TLS impersonation (Akamai blocks bare httpx). Heading-boundary chunks on Privacy and T&C. Prop 65 / SDS / green-building from Assist, cross-tagged Legal.

### Meridian HR and Finance (synthetic)

I wrote the Markdown myself. Not an "LLM, generate a Kohler policy" artifact. Structure informed by reference PDFs for section conventions only. SYNTHETIC banner in each file. Finance encodes unambiguous ₹ bands on purpose.

### Index

One Chroma collection `prism_kb` plus a BM25 sidecar. Embeddings: `nomic-embed-text`. Role flags and `source_priority` are metadata at ingest. Rebuild: `python -m prism.ingest.build_index`. Expected ~519 chunks.

---

## 11. Eval uses the same path

`eval/bench_models.py` and `eval/run_eval.py` call the same `generate_answer()` as production. There is no secret eval prompt.

| Harness | What it scores | Prompt |
|---|---|---|
| 12 golden questions | Schema, fact recall, Finance exactness, latency, VRAM | `SYSTEM_PROMPT` |
| 40 routing questions | Domain accuracy, hit@5, ms | None (no generator) |
| 39 stress cases | Numeric edges, jailbreak, formats, clarify, honesty | Same gates + `SYSTEM_PROMPT` when a generate happens |
| RBAC smoke | Four roles, named-record deny | `rbac_deny` path |

A judge clones the repo, starts the API, and runs `uv run python -m eval.stress.harness`.

---

## 12. Workflow index

| `workflow` | Meaning | Chapter |
|---|---|---|
| `rag_canonical` | Hybrid retrieve → `SYSTEM_PROMPT` → prose | 6 |
| `rag_email` | Same RAG path, then email renderer | 6, 7 |
| `policy_math` | Deterministic leave / INR bands | 8 |
| `rbac_deny` | Role denied before retrieval | 8 |
| `jailbreak_refuse` | Prompt exfil / developer mode | 8 |
| `policy_override_refuse` | CFO spoof / ₹0 override | 8 |
| `reformat` | Replay `last_answer` only | 5, 8 |
| `clarify` | Ambiguous domain | 8 |
| `session_memory` | History lookback, no RAG | 5 |
| `session_email_recall` | Earlier fact → email | 5 |
| `upload_rag` | Session file | 8 |

---

## 13. File map

| Path | What a judge opens |
|---|---|
| `prism/core/answer.py` | `SYSTEM_PROMPT`, user template, repair |
| `prism/core/agent.py` | Gate order, `workflow` id, `extra_notes` |
| `prism/core/titler.py` | Title prompt |
| `prism/core/renderers/email.py` | Template email + optional polish (off) |
| `prism/core/router.py` | Anchor phrases |
| `prism/core/policy_math.py` | CL / INR |
| `prism/core/rbac.py` · `auth.py` | Roles, tokens |
| `prism/core/text_utils.py` | Jailbreak / override detectors |
| `prism/core/answer_polish.py` | Citations, soft refuse, source priority |
| `prism/core/water_math.py` | EPA liters/day |
| `prism/core/uploads.py` | Session collection |
| `frontend/src/App.tsx` | Workflow chip, Stitch-inspired landing type |
| `docs/pdf/deck.pdf` | Jury slides |
| `docs/pdf/system_guide.pdf` | Long-form teaching pass |

Keep this file updated when a prompt or workflow changes. Regenerate with `python scripts/export_prompts.py`.
