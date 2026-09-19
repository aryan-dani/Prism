# Prism — Demo Script (1–3 minutes)

Record this exact flow. It hits numeric exactness, domain switch, **live upload**, water-conservation callout, and multi-format render.

## Setup before recording
1. Ollama running; generation model loaded (`qwen2.5:7b-instruct`).
2. API: `uv run uvicorn prism.api.main:app --port 8000`
3. UI: `cd frontend; npm run dev` → http://localhost:5173
4. Start on the **landing page**, then enter chat. Full screen. Hide personal desktop clutter.
5. Have a small markdown/PDF on the desktop (e.g. a one-page “Orion travel policy” with a ₹3,250 per-diem).

## Script (~2:20)

**0:00–0:20 — Hook (lead with the upload)**  
Landing: “One query, any format.” Click **Try the live demo**.  
Drop `orion_travel_policy.md` onto the composer. Wait for the “active” chip.  
Ask: `According to this document, who approves a claim of INR 45,000?`  
Expect: domain chip **uploaded doc**, “department head”, source `upload://…`.  
Voiceover: “A sixth domain that exists only for this chat — parsed, embedded, and answered locally. Delete the session and the vectors go with it.”

**0:20–0:45 — Finance exactness (five KBs still work)**  
New conversation. Ask: `An employee submits an expense claim for ₹15,000. Who needs to approve it?`  
Expect: Reporting Manager, band ₹5,001–₹25,000, Finance chip.

**0:45–1:10 — Domain switch + water callout**  
Ask: `My toilet is occasionally leaking or running — what should I check?`  
Expect: Customer Support chip, trip-lever / flapper steps, **green water-conservation callout** with EPA liters/day.  
Voiceover: “Mid-conversation domain switch — and a labeled water-waste estimate from published EPA figures, not the model.”

**1:10–1:25 — Anaphora**  
Ask: `actually is that covered under warranty`  
Expect: a warranty-aware follow-up, not a repeat of the flapper steps.

**1:25–1:55 — One answer, five formats**  
On the Finance or Support answer: **Prose → JSON → XML → Excel download → Email**.  
Voiceover: “Same canonical object — no re-retrieval.”

**1:55–2:10 — Close**  
“Runs fully local on Ollama within 8GB VRAM. Prism — one query, any format.”

## Checklist while editing
- [ ] Landing page in the first 10 seconds
- [ ] Upload chip “active” + “Local only · purged with this chat”
- [ ] Water callout visible
- [ ] Session title auto-updating
- [ ] Excel actually downloading
- [ ] Caption: “Academic case study · synthetic HR/Finance · real Kohler Support/Privacy/Legal · uploads stay on-device”


## Checklist while editing
- [ ] Show session title auto-updating after first turn
- [ ] Show sources under an assistant bubble
- [ ] Show Excel actually downloading
- [ ] No long silent waits — cut dead air while the model thinks
- [ ] Caption: “Academic case study · synthetic HR/Finance · real Kohler Support/Privacy/Legal”

## Upload
Upload to YouTube/Drive unlisted; put the link in README under **Demo video**.
