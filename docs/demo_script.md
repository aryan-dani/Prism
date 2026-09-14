# Prism — Demo Script (1–3 minutes)

Record this exact flow. It deliberately hits the evaluation beats: numeric exactness, domain switch, clarification, and multi-format render from one canonical answer.

## Setup before recording
1. Ollama running; generation model loaded (`qwen2.5:7b-instruct` or the winner from `docs/decisions.md` §3).
2. API: `uv run uvicorn prism.api.main:app --port 8000`
3. UI: `cd web; npm run dev` → http://localhost:5173
4. New conversation. Full screen. Hide personal desktop clutter.

## Script (~2:00)

**0:00–0:15 — Hook**  
Voiceover: “Prism is one local agent across five Kohler enterprise domains — HR, Finance, Customer Support, Privacy, and Legal — with answers you can reformat on demand.”  
Show the empty state with domain chips.

**0:15–0:40 — Finance exactness**  
Ask: `An employee submits an expense claim for ₹15,000. Who needs to approve it?`  
Expect: Reporting Manager (band ₹5,001–₹25,000), high confidence, Finance domain chip.  
Voiceover: “Hard numeric thresholds — the agent has to get the band exactly right.”

**0:40–1:05 — Domain switch (no restating context)**  
Ask: `My toilet is occasionally leaking or running — what should I check?`  
Expect: domain chip flips to Customer Support; steps about trip lever / flapper / canister.  
Voiceover: “Mid-conversation domain switch — retrieval re-routes without a new session.”

**1:05–1:25 — Anaphora follow-up**  
Ask: `What about that flapper seal you mentioned?`  
Expect: grounded follow-up using prior context.

**1:25–1:45 — Clarification moment**  
New chat (or a deliberately ambiguous ask): `What's the policy on returns and leave?`  
Expect: clarification question with HR vs Customer Support (or similar) — answer the chip.  
Voiceover: “When routing is ambiguous, Prism asks — it doesn’t guess.”

**1:45–2:10 — One answer, five formats**  
Back on a solid Finance or Support answer. Click format bar: **JSON → XML → Excel download → Email**.  
Voiceover: “Same canonical answer object — no re-retrieval, no re-prompting.”

**2:10–2:20 — Close**  
“Runs fully local on Ollama within 8GB VRAM. Prism — one query, any format.”

## Checklist while editing
- [ ] Show session title auto-updating after first turn
- [ ] Show sources under an assistant bubble
- [ ] Show Excel actually downloading
- [ ] No long silent waits — cut dead air while the model thinks
- [ ] Caption: “Academic case study · synthetic HR/Finance · real Kohler Support/Privacy/Legal”

## Upload
Upload to YouTube/Drive unlisted; put the link in README under **Demo video**.
