# Prism Stress-Test Report

- Generated: `2026-09-18T12:07:18.746251+00:00`
- API: `http://127.0.0.1:8000`
- Health: `{"status": "ok", "chunks_indexed": 497, "embed_model": "nomic-embed-text", "gen_model": "qwen2.5:7b-instruct", "title_model": "qwen2.5:3b-instruct", "domains": ["hr", "finance", "customer_support", "privacy", "legal"], "ollama": {"reachable": true, "host": "http://localhost:11434", "models_required": ["nomic-embed-text", "qwen2.5:7b-instruct", "qwen2.5:3b-instruct"], "models_missing": [], "ok": true}, "uploads": {"chunks_indexed": 0, "ttl_hours": 24.0, "max_bytes": 12582912, "allowed_suffixes": [".csv", ".docx", ".htm", ".html", ".json", ".markdown", ".md", ".pdf", ".txt"]}}`
- Cases run: **7**
- Wall time: **241s**

## Summary by category

| Category | PASS | PARTIAL | FAIL | NEEDS_HUMAN_REVIEW | SKIP |
|---|---:|---:|---:|---:|---:|
| 3_silent_domain_switch | 2 | 1 | 0 | 0 | 0 |
| 5_long_range_multiturn | 0 | 1 | 0 | 0 | 0 |
| 2_cross_domain_multihop | 1 | 0 | 0 | 0 | 0 |
| 4_ambiguity_clarify | 1 | 0 | 0 | 0 | 0 |
| 6_hallucination_honesty | 1 | 0 | 0 | 0 | 0 |
| **TOTAL** | **5** | **2** | **0** | **0** | **0** |

## FAIL and PARTIAL detail (worst categories first)

### 3_silent_domain_switch

#### `switch_02_toilet_warranty_refund` — Toilet fix → warranty → refund → **PARTIAL**

- **PARTIAL** [expect] latency 23.5s > 20s threshold
**Turn 0** (7.4s) user: My toilet is occasionally leaking or running — what should I check first?

```
First, check the trip lever chain for proper slack. Remove excess chain if needed, as this can prevent the chain from getting caught on the trip lever arm.

- Trip lever chain adjustment: Adjust the chain to have roughly one to two links of slack.

1. Adjust the trip lever chain for proper slack. The chain should have roughly one to two links of slack at most so the excess chain does not get caught on the trip lever arm. Remove excess chain if needed.

Sources: https://assist.kohler.com/en/toilets-and-seats/Toilet-Occasionally-Leaking-or-Running
```

domain=`customer_support` confidence=`high` clarification=`False` no_answer=`False` title=`Toilet leak troubleshooting first steps`

**Turn 1** (13.3s) user: actually is that covered under warranty

```
The troubleshooting steps for adjusting the trip lever chain are not explicitly stated to be covered under warranty, but the issue of a toilet occasionally leaking or running is within the scope of the limited warranty for mechanical components.

- Warranty Coverage: Limited Warranty for Mechanical Components

Sources: https://assist.kohler.com/en/toilets-and-seats/Toilet-Occasionally-Leaking-or-Running
```

domain=`customer_support` confidence=`medium` clarification=`False` no_answer=`False` title=`Toilet leak troubleshooting first steps`

**Turn 2** (23.5s) user: and if it's not, can I get a refund instead

```
First, check the trip lever chain for proper slack. If the issue persists, you may be eligible for a refund within 90 days of shipment, provided the product is in new and saleable condition.

- First Step: Check the trip lever chain for proper slack.
- Return Policy: Items may be returned for a refund within 90 days of shipment.

1. Check the trip lever chain for proper slack.
2. If the issue persists, contact Kohler customer service to request a return authorization.
3. Follow the instructions to start a return and ship the product back to the approved Kohler.com warehouse.

Note: The product must be in new and saleable condition. You are responsible for coordinating the return shipment and related costs.

Sources: https://assist.kohler.com/en/toilets-and-seats/VIDEO-How-to-Flush-the-Fill-Valve-on-KOHLER-Two-Piece-Toilets, https://assist.kohler.com/en/orders-and-returns/Return-Policy
```

domain=`customer_support` confidence=`medium` clarification=`False` no_answer=`False` title=`Toilet leak troubleshooting first steps`

---

### 5_long_range_multiturn

#### `long_01_12turn_carryforward_email` — 12-turn memory: retrieve early CL carry-forward + email → **PARTIAL**

- **PARTIAL** [latency_series_flag] latencies=[9.4, 12.5, 18.9, 0.0, 13.0, 35.9, 15.5, 14.7, 11.1, 11.6, 0.1, 0.0]; turns over 20s: [5]
**Turn 0** (9.4s) user: How many casual leave days can I carry forward to the next leave year?

```
You can carry forward up to 5 unused casual leave days to the next leave year.

- Maximum Carry-Forward Days: 5 days

Sources: data/synthetic/hr_policy.md
```

domain=`hr` confidence=`high` clarification=`False` no_answer=`False` title=`Casual Leave Carryover Rules`

**Turn 1** (12.5s) user: And is casual leave encashable when I resign?

```
Casual leave is not encashable when you resign.

- Maximum Carry-Forward Days: 5 days
- Encashment at Resignation: Not encashable

Sources: data/synthetic/hr_policy.md
```

domain=`hr` confidence=`high` clarification=`False` no_answer=`False` title=`Casual Leave Carryover Rules`

**Turn 2** (18.9s) user: What's the per diem rate for a business trip to Mumbai?

```
The per diem rate for a business trip to Mumbai is ₹2,000 per day.

- Per Diem Rate for Mumbai: ₹2,000 per day

City Tier | Per Diem (per day)
--- | ---
Tier-1 (Mumbai, Delhi NCR, Bengaluru, Chennai, Kolkata, Hyderabad, Pune) | ₹2,000

Sources: data/synthetic/finance_policy.md
```

domain=`finance` confidence=`high` clarification=`False` no_answer=`False` title=`Casual Leave Carryover Rules`

**Turn 3** (0.0s) user: Who approves an expense claim of ₹40,000?

```
A claim of ₹40,000 falls in the ₹25,001 to ₹100,000 band and requires Department Head sign-off in addition to the Reporting Manager.

- Claim amount: ₹40,000
- Approval band: ₹25,001 to ₹100,000
- Required approval: Department Head sign-off (in addition to Reporting Manager)

Note: Approval authority looked up from Finance Policy Section 2.1 bands in code (total claim value, not line items).

Sources: data/synthetic/finance_policy.md
```

domain=`finance` confidence=`high` clarification=`False` no_answer=`False` title=`Casual Leave Carryover Rules`

**Turn 4** (13.0s) user: My Kohler kitchen faucet is leaking from the end of the spout — what could cause that?

```
Could you provide more details about the faucet model or any recent changes made to it?
```

domain=`finance` confidence=`high` clarification=`True` no_answer=`False` title=`Casual Leave Carryover Rules`

**Turn 5** (35.9s) user: How do I remove an aerator?

```
To remove the aerator, you need to locate it first. For some models, you can slide a fingernail over the end of the spout to find the connection. Once located, you can unthread the aerator by hand. For other models, you may need to use an adjustable wrench or specific tools like a hex key wrench or needle nose pliers.

- Aerators Location: Located in the spray face of the sprayhead or at the end of the spout
- Removal Tools: Adjustable wrench, needle nose pliers or tweezers, hex key wrench

1. Locate the aerator by sliding a fingernail over the end of the spout or finding the connection in the spray face of the sprayhead.
2. Use an adjustable wrench or needle nose pliers to unthread the aerator by hand.
3. For specific models, use a hex key wrench to remove the set screw and then use needle nose pliers to pull the stream breaker out.
4. Clean the stream breaker with a 50/50 solution of white vinegar and warm water if necessary.

Sources: https://assist.kohler.com/en/kitchen-faucets/Removing-an-aerator, https://assist.kohler.com/en/bathroom-faucets/Katun-Faucet-Stream-Breaker-Removal, https://assist.kohler.com/en/kitchen-faucets/K-R10651-SD-Sous-Kitchen-Sink-Faucet-Spring-Removal
```

domain=`customer_support` confidence=`medium` clarification=`False` no_answer=`False` title=`Casual Leave Carryover Rules`

**Turn 6** (15.5s) user: What personal information does the Kohler privacy policy say is collected?

```
Kohler's legal bases for processing personal information include Execution of a Contract, Legitimate Interests, Compliance with Law, and Consent.

- Legal Bases: Execution of a Contract, Legitimate Interests, Compliance with Law, Consent

Legal Basis | Purpose
--- | ---
Execution of a Contract | To provide the products or services we have agreed to deliver to you.
Legitimate Interests | To deliver excellent service and ensure our products and services are customized to meet your specific needs and preferences.
Compliance with Law | To comply with a legal or regulatory obligation.
Consent | For optional cookies used for marketing purposes.

Sources: https://www.kohler.com/en/legal/privacy-policy
```

domain=`privacy` confidence=`high` clarification=`False` no_answer=`False` title=`Casual Leave Carryover Rules`

**Turn 7** (14.7s) user: Does Kohler offer California Proposition 65 information?

```
You can opt-out of tracking for targeted advertising purposes or other sales of Personal Information via email, phone, or by navigating to the ‘Do Not Sell or Share My Personal Information’ link on any Kohler website.

- Opt-out methods: Email: KohlerGlobalDataPrivacy@kohler.com, Phone: 1-800-923-1138, Website: ‘Do Not Sell or Share My Personal Information’ link

1. Navigate to any Kohler website
2. Click on the ‘Do Not Sell or Share My Personal Information’ link
3. Follow the instructions provided
4. Send an email to KohlerGlobalDataPrivacy@kohler.com
5. Call 1-800-923-1138

Sources: https://www.kohler.com/en/legal/privacy-policy
```

domain=`privacy` confidence=`high` clarification=`False` no_answer=`False` title=`Casual Leave Carryover Rules`

**Turn 8** (11.1s) user: What's the notice period for a confirmed manager resigning?

```
The notice period for a confirmed manager (Grade M1 and above) is 60 days.

- Notice Period for Confirmed Managers: 60 days

Sources: data/synthetic/hr_policy.md
```

domain=`hr` confidence=`high` clarification=`False` no_answer=`False` title=`Casual Leave Carryover Rules`

**Turn 9** (11.6s) user: What is the standard vendor payment term (Net X)?

```
The standard vendor payment term at Kohler is Net 45 from the invoice approval date, unless a different term is specified in the vendor's master agreement.

- Standard Payment Term: Net 45 days

Sources: data/synthetic/finance_policy.md
```

domain=`finance` confidence=`high` clarification=`False` no_answer=`False` title=`Casual Leave Carryover Rules`

**Turn 10** (0.1s) user: wait, what did I ask you two questions ago?

```
Two questions ago you asked: "What's the notice period for a confirmed manager resigning?"

Note: Answered from this session's conversation history, not from the knowledge base.
```

domain=`hr` confidence=`high` clarification=`False` no_answer=`False` title=`Casual Leave Carryover Rules`

**Turn 11** (0.0s) user: going back to what you told me about the leave carry-forward limit near the start of this conversation, can you draft an email to my manager summarizing that fact along with today's date?

```
Subject: Re: Going back to what you told me about the leave carry-forward limit near the s...

Hi there,

As of today (2026-09-18), casual leave carry-forward is capped at 5 unused CL days into the next leave year, per HR policy (as confirmed earlier in this conversation).

Key details:
  - CL carry-forward maximum: 5 days

Please note: Recalled from earlier turns in this session; aligned with HR leave policy.

Reference: data/synthetic/hr_policy.md

Best regards,
Prism Assistant
```

domain=`hr` confidence=`high` clarification=`False` no_answer=`False` title=`Casual Leave Carryover Rules`

---

## NEEDS_HUMAN_REVIEW items

_None._

## All case rollups

- `xdom_03_loaded_privacy_premise` [2_cross_domain_multihop]: **PASS**
- `switch_01_training_reimburse` [3_silent_domain_switch]: **PASS**
- `switch_03_sticky_hr_to_faucet` [3_silent_domain_switch]: **PASS**
- `switch_02_toilet_warranty_refund` [3_silent_domain_switch]: **PARTIAL**
- `amb_02_extension` [4_ambiguity_clarify]: **PASS**
- `long_01_12turn_carryforward_email` [5_long_range_multiturn]: **PARTIAL**
- `hall_03_leading_manager_number` [6_hallucination_honesty]: **PASS**