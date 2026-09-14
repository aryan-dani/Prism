"""Domain routing without a full LLM call.

Two cheap, complementary signals (see docs/decisions.md Section 4):
  1. Cosine similarity between the query embedding and a curated set of
     domain-representative "anchor phrases" -- the kind of question a real
     user would ask in that domain. This costs zero extra LLM/embedding
     calls beyond the one embedding we already need for retrieval.
  2. A vote over which domain the top-K domain-agnostic retrieval hits
     belong to -- confirms/overrides the anchor signal using the actual
     corpus content, which matters for phrasing the anchors don't anticipate.

The two are blended; if the result is still too close to call, the caller
(agent.py) asks a clarifying question instead of guessing (Piece 7).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from prism.core.config import ROUTER_AMBIGUITY_MARGIN, ROUTER_MIN_CONFIDENCE

ANCHOR_PHRASES: dict[str, list[str]] = {
    "hr": [
        "how many casual leave days do I get per year",
        "what is the notice period for resigning",
        "how does the grievance redressal process work",
        "what is the work from home policy",
        "how many sick leave days can I carry forward",
        "what happens during a disciplinary inquiry",
        "what is the probation period for new employees",
        "how do I request maternity or paternity leave",
        "what is the code of conduct for employees",
        "how is a performance improvement plan run",
        "what is the employee referral bonus process",
        "how do I resign and what is the exit process",
    ],
    "finance": [
        "what is the approval limit for expense claims",
        "how much per diem do I get for business travel",
        "when is a purchase order required for an invoice",
        "what is the reimbursement limit for hotel stays",
        "who needs to sign off on an expense above a certain amount",
        "what are the invoice submission timelines",
        "what is the overtime pay rate",
        "how is the annual budget allocated across departments",
        "what is the capital expenditure approval threshold",
        "what is the payment term for vendor invoices",
        "how much can I claim without a receipt",
        "what is the budget variance reporting requirement",
    ],
    "customer_support": [
        "my toilet is leaking or running occasionally",
        "how do I replace a faucet cartridge",
        "the shower valve is not getting hot water",
        "how do I install a new kitchen faucet",
        "my bathtub drain is clogged",
        "how do I find my product's model number",
        "the shower door is not sliding smoothly",
        "how do I register my Kohler product",
        "what is the return policy for a purchase",
        "how do I track my order status",
        "what does this error code on my digital valve mean",
        "how do I clean and maintain my sink",
    ],
    "privacy": [
        "what personal information does Kohler collect",
        "how do I opt out of having my data sold or shared",
        "does Kohler use cookies to track me",
        "how can I request deletion of my personal data",
        "what is Kohler's privacy policy",
        "does Kohler share my data with third parties",
        "how do I exercise my CCPA rights",
        "what data does Kohler collect from my account",
        "how long does Kohler retain my personal information",
        "can I access the personal data Kohler has about me",
    ],
    "legal": [
        "what are Kohler's terms and conditions",
        "are Kohler products compliant with California Proposition 65",
        "does Kohler provide safety data sheets for its products",
        "what is the warranty dispute resolution process",
        "does Kohler offer product transparency documents for green building certifications",
        "what are the terms of sale for Kohler products",
        "what is covered under the product warranty",
        "what is the liability limitation in the terms of use",
        "is there an arbitration clause for disputes",
        "what are the terms for using the kohler.com website",
    ],
}


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


_anchor_embeddings: dict[str, list[list[float]]] | None = None


def _get_anchor_embeddings() -> dict[str, list[list[float]]]:
    global _anchor_embeddings
    if _anchor_embeddings is None:
        from prism.core.embeddings import embed_batch

        _anchor_embeddings = {domain: embed_batch(phrases) for domain, phrases in ANCHOR_PHRASES.items()}
    return _anchor_embeddings


@dataclass
class RouteResult:
    domain: str | None  # None when ambiguous
    scores: dict[str, float]
    confidence: float
    ambiguous: bool
    reason: str


def score_by_anchors(query_embedding: list[float]) -> dict[str, float]:
    """Best-anchor cosine similarity per domain (max, not average -- a query
    only needs to strongly match ONE representative phrase in a domain)."""
    anchors = _get_anchor_embeddings()
    scores: dict[str, float] = {}
    for domain, embeddings in anchors.items():
        scores[domain] = max(cosine_similarity(query_embedding, e) for e in embeddings)
    return scores


def score_by_hit_votes(hits: list) -> dict[str, float]:
    """Vote share of domain-agnostic top-K retrieval hits, weighted by rank
    (earlier hits count more). `hits` are RetrievedChunk-like objects with
    `.metadata['domain']` and `.dense_rank`."""
    if not hits:
        return {}
    weights: dict[str, float] = {}
    total = 0.0
    for h in hits:
        rank = h.dense_rank if h.dense_rank is not None else 0
        w = 1.0 / (rank + 1)
        d = h.metadata.get("domain")
        if d:
            weights[d] = weights.get(d, 0.0) + w
            total += w
    if total == 0:
        return {}
    return {d: w / total for d, w in weights.items()}


def route(
    query_embedding: list[float],
    *,
    hit_votes: dict[str, float] | None = None,
    sticky_domain: str | None = None,
    anchor_weight: float = 0.7,
    vote_weight: float = 0.3,
) -> RouteResult:
    """Combine anchor similarity + hit-vote signals into a routing decision.

    `sticky_domain`: the previous turn's active domain. Short/anaphoric
    follow-ups often score weakly on anchors (e.g. "how many days is that?")
    -- if the blended scores are ambiguous AND a sticky domain exists, prefer
    staying in that domain rather than asking for clarification, UNLESS
    another domain clearly outscores it (a genuine topic switch).
    """
    anchor_scores = score_by_anchors(query_embedding)
    votes = hit_votes or {}

    combined: dict[str, float] = {}
    for domain in anchor_scores:
        combined[domain] = anchor_weight * anchor_scores[domain] + vote_weight * votes.get(domain, 0.0)

    ranked = sorted(combined.items(), key=lambda kv: -kv[1])
    best_domain, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = best_score - second_score

    if best_score < ROUTER_MIN_CONFIDENCE:
        if sticky_domain:
            return RouteResult(
                domain=sticky_domain,
                scores=combined,
                confidence=best_score,
                ambiguous=False,
                reason="below confidence floor; staying in sticky domain",
            )
        return RouteResult(
            domain=None, scores=combined, confidence=best_score, ambiguous=True, reason="below confidence floor"
        )

    if margin < ROUTER_AMBIGUITY_MARGIN:
        if sticky_domain and sticky_domain in (ranked[0][0], ranked[1][0]):
            return RouteResult(
                domain=sticky_domain,
                scores=combined,
                confidence=combined.get(sticky_domain, best_score),
                ambiguous=False,
                reason="ambiguous margin, but sticky domain is one of the top contenders",
            )
        return RouteResult(
            domain=None,
            scores=combined,
            confidence=best_score,
            ambiguous=True,
            reason=f"top two domains within {ROUTER_AMBIGUITY_MARGIN} margin",
        )

    return RouteResult(domain=best_domain, scores=combined, confidence=best_score, ambiguous=False, reason="clear winner")
