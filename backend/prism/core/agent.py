"""The Prism agent state machine (hand-rolled, per the plan's orchestration
decision -- see docs/decisions.md Section 5).

Turn flow:
    user message
      -> jailbreak / policy-override refuse (deterministic, no LLM)
      -> deterministic leave arithmetic when pattern matches (no LLM math)
      -> is this a reformat-only request?
      -> clarification resolve / vague-session clarify
      -> route + retrieve (per-domain merge for multi-hop)
      -> generate ONE canonical answer
      -> store + render prose
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from prism.core.answer import CanonicalAnswer, generate_answer, no_context_answer
from prism.core.memory import SessionState, SourceDocRef
from prism.core.policy_math import try_deterministic_policy_answer
from prism.core.renderers import FormatName, RenderResult, render as render_format
from prism.core.renderers import excel as excel_renderer
from prism.core.retriever import RetrievalResult, retrieve
from prism.core.router import route, score_by_hit_votes
from prism.core.text_utils import (
    asks_for_fabricated_schema_fields,
    extract_claimed_inr_amounts,
    extract_model_numbers,
    is_contractor_damage_query,
    is_false_premise_probe,
    is_leading_numeric_claim,
    is_policy_override_attempt,
    is_prompt_exfil_or_jailbreak,
    needs_multi_domain_retrieval,
    signaled_domains,
    vague_new_session_clarify,
)
from prism.core.store import RetrievedChunk

REFORMAT_PATTERNS: dict[FormatName, re.Pattern] = {
    "json": re.compile(r"\b(as|in|to)?\s*json\b", re.IGNORECASE),
    "xml": re.compile(r"\b(as|in|to)?\s*xml\b", re.IGNORECASE),
    "excel": re.compile(r"\b(excel|xlsx|spreadsheet|download.*sheet)\b", re.IGNORECASE),
    "email": re.compile(r"\b(email|draft.*mail|send.*mail)\b", re.IGNORECASE),
    "prose": re.compile(r"\b(plain|prose|normal|regular)\s*(text|answer|format)?\b", re.IGNORECASE),
}

ANAPHORA_RE = re.compile(r"\b(that|this|it|those|the one|the last one|you mentioned|previous)\b", re.IGNORECASE)

CLARIFY_DOMAIN_LABELS = {
    "hr": "an HR policy question (leave, conduct, WFH, etc.)",
    "finance": "a Finance policy question (reimbursement, budgets, approvals)",
    "customer_support": "a product troubleshooting/support question",
    "privacy": "a privacy/data-handling question",
    "legal": "a legal/compliance question (terms, warranty, regulatory)",
}

DESIGN_SERVICE_NOISE = ("bathroom design service", "mood board", "virtual design meeting")


@dataclass
class TurnResult:
    session: SessionState
    reply_text: str
    render_result: RenderResult
    answer: CanonicalAnswer | None
    domain: str | None
    is_clarification: bool
    is_reformat: bool


def detect_reformat_request(message: str) -> FormatName | None:
    for fmt, pattern in REFORMAT_PATTERNS.items():
        if pattern.search(message):
            return fmt
    return None


def _refuse(session: SessionState, user_message: str, reply: str, *, domain: str | None = None) -> TurnResult:
    session.add_turn("user", user_message)
    answer = CanonicalAnswer(
        query=user_message,
        domain=domain or session.active_domain or "hr",
        direct_answer=reply,
        confidence="none",
        no_answer=True,
    )
    session.last_answer = answer
    session.add_turn("assistant", reply, domain=domain or session.active_domain)
    return TurnResult(
        session=session,
        reply_text=reply,
        render_result=RenderResult(format="prose", content=reply, mime_type="text/plain"),
        answer=answer,
        domain=domain or session.active_domain,
        is_clarification=False,
        is_reformat=False,
    )


def _commit_answer(
    session: SessionState,
    *,
    answer: CanonicalAnswer,
    domain: str | None,
    chunks: list[RetrievedChunk] | None = None,
) -> TurnResult:
    session.active_domain = domain
    session.last_answer = answer
    if chunks:
        session.last_docs = [
            SourceDocRef(
                id=c.id,
                title=c.metadata.get("title", ""),
                source_url=c.metadata.get("source_url", ""),
                domain=c.metadata.get("domain", ""),
                text=c.text,
            )
            for c in chunks[:5]
        ]
    rr = render_format(answer, "prose")
    session.add_turn("assistant", rr.content, domain=domain)
    return TurnResult(
        session=session,
        reply_text=rr.content,
        render_result=rr,
        answer=answer,
        domain=domain,
        is_clarification=False,
        is_reformat=False,
    )


def _filter_noise_chunks(query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    if not is_contractor_damage_query(query):
        return chunks
    filtered = []
    for c in chunks:
        blob = f"{c.metadata.get('title', '')} {c.text}".lower()
        if any(n in blob for n in DESIGN_SERVICE_NOISE):
            continue
        filtered.append(c)
    return filtered or chunks


def _retrieve_for_query(query: str, *, domain: str | None, multi_domain: bool) -> RetrievalResult:
    if multi_domain:
        domains = signaled_domains(query) or (["customer_support", "legal"] if is_contractor_damage_query(query) else [])
        if is_contractor_damage_query(query):
            for d in ("customer_support", "legal"):
                if d not in domains:
                    domains.append(d)
        if not domains:
            domains = ["hr", "finance", "privacy", "customer_support", "legal"]

        by_id: dict[str, RetrievedChunk] = {}
        best_distance: float | None = None
        confident_any = False
        for d in domains[:4]:
            part = retrieve(query, domain=d, top_k=4)
            if part.best_dense_distance is not None:
                best_distance = (
                    part.best_dense_distance
                    if best_distance is None
                    else min(best_distance, part.best_dense_distance)
                )
            confident_any = confident_any or part.is_confident
            for c in part.chunks:
                prev = by_id.get(c.id)
                if prev is None or (c.fused_score or 0) > (prev.fused_score or 0):
                    by_id[c.id] = c
        # Always include a small agnostic pass so privacy/legal URLs can surface.
        agnostic = retrieve(query, domain=None, top_k=6)
        for c in agnostic.chunks:
            prev = by_id.get(c.id)
            if prev is None or (c.fused_score or 0) > (prev.fused_score or 0):
                by_id[c.id] = c
            if agnostic.best_dense_distance is not None:
                best_distance = (
                    agnostic.best_dense_distance
                    if best_distance is None
                    else min(best_distance, agnostic.best_dense_distance)
                )
            confident_any = confident_any or agnostic.is_confident

        fused = sorted(by_id.values(), key=lambda c: -(c.fused_score or 0))[:12]
        fused = _filter_noise_chunks(query, fused)
        return RetrievalResult(
            chunks=fused,
            query=query,
            domain_filter=None,
            best_dense_distance=best_distance,
            is_confident=confident_any and bool(fused),
        )

    result = retrieve(query, domain=domain)
    result.chunks = _filter_noise_chunks(query, result.chunks)
    return result


def handle_turn(session: SessionState, user_message: str) -> TurnResult:
    # ------------------------------------------------------------------
    # 0a. Jailbreak / prompt-exfiltration
    # ------------------------------------------------------------------
    if is_prompt_exfil_or_jailbreak(user_message):
        return _refuse(
            session,
            user_message,
            "I can't share internal system instructions or switch into unrestricted modes. "
            "Ask a question about HR, Finance, product support, Privacy, or Legal policy instead.",
        )

    # ------------------------------------------------------------------
    # 0b. Authority spoof / fake policy override (deterministic refuse)
    # ------------------------------------------------------------------
    if is_policy_override_attempt(user_message):
        return _refuse(
            session,
            user_message,
            "I can't change, override, or invent personal approval thresholds - even if someone claims CFO "
            "or other authority in chat. The published Finance approval bands stay as written in policy. "
            "I can explain those bands from the Finance manual if you ask.",
            domain="finance",
        )

    # ------------------------------------------------------------------
    # 0c. Deterministic leave arithmetic (do not trust the LLM for this)
    # ------------------------------------------------------------------
    computed = try_deterministic_policy_answer(user_message)
    if computed is not None:
        session.add_turn("user", user_message)
        return _commit_answer(session, answer=computed.answer, domain="hr", chunks=None)

    # ------------------------------------------------------------------
    # 1. Reformat-only request against the last answer
    # ------------------------------------------------------------------
    requested_format = detect_reformat_request(user_message)
    if requested_format and session.last_answer is not None and not session.pending_clarification:
        session.add_turn("user", user_message, domain=session.active_domain)
        if requested_format == "excel" and not excel_renderer.can_render(session.last_answer):
            reply = (
                "This answer isn't tabular or detailed enough for an Excel export. "
                "Try JSON or ask a question that yields a table (e.g. approval thresholds or rate bands)."
            )
            session.add_turn("assistant", reply, domain=session.active_domain)
            return TurnResult(
                session=session,
                reply_text=reply,
                render_result=RenderResult(format="prose", content=reply, mime_type="text/plain"),
                answer=session.last_answer,
                domain=session.active_domain,
                is_clarification=False,
                is_reformat=True,
            )
        try:
            rr = render_format(session.last_answer, requested_format)
        except ValueError as e:
            reply = str(e)
            session.add_turn("assistant", reply, domain=session.active_domain)
            return TurnResult(
                session=session,
                reply_text=reply,
                render_result=RenderResult(format="prose", content=reply, mime_type="text/plain"),
                answer=session.last_answer,
                domain=session.active_domain,
                is_clarification=False,
                is_reformat=True,
            )
        reply = rr.content if not rr.is_binary else f"(Generated a downloadable {requested_format} file.)"
        session.add_turn("assistant", reply if isinstance(reply, str) else "[binary output]", domain=session.active_domain)
        return TurnResult(
            session=session,
            reply_text=reply if isinstance(reply, str) else "",
            render_result=rr,
            answer=session.last_answer,
            domain=session.active_domain,
            is_clarification=False,
            is_reformat=True,
        )

    # ------------------------------------------------------------------
    # 2. Resolve a pending clarification
    # ------------------------------------------------------------------
    forced_domain: str | None = None
    effective_query = user_message
    if session.pending_clarification:
        chosen = _match_domain_from_reply(user_message, session.pending_clarification.candidate_domains)
        if chosen:
            forced_domain = chosen
            effective_query = session.pending_clarification.original_query + " " + user_message
        session.pending_clarification = None

    session.add_turn("user", user_message)

    # ------------------------------------------------------------------
    # 2b. Brand-new session, intentionally vague queries
    # ------------------------------------------------------------------
    vague_domains = vague_new_session_clarify(user_message, has_prior_turns=len(session.turns) > 1)
    if vague_domains and not forced_domain:
        question = (
            "I want to make sure I point you to the right place — is this "
            + " or ".join(CLARIFY_DOMAIN_LABELS.get(d, d) for d in vague_domains[:3])
            + "?"
        )
        from prism.core.memory import PendingClarification

        session.pending_clarification = PendingClarification(
            original_query=user_message, question=question, candidate_domains=vague_domains[:3]
        )
        session.add_turn("assistant", question, domain=None)
        return TurnResult(
            session=session,
            reply_text=question,
            render_result=RenderResult(format="prose", content=question, mime_type="text/plain"),
            answer=None,
            domain=None,
            is_clarification=True,
            is_reformat=False,
        )

    # ------------------------------------------------------------------
    # 3. Anaphora + flags
    # ------------------------------------------------------------------
    retrieval_query = effective_query
    if ANAPHORA_RE.search(effective_query) and session.turns:
        retrieval_query = f"{session.recent_context_str(4)}\n{effective_query}"

    multi_domain = needs_multi_domain_retrieval(effective_query) or is_contractor_damage_query(effective_query)
    model_nums = extract_model_numbers(effective_query)
    leading = is_leading_numeric_claim(effective_query)
    false_premise = is_false_premise_probe(effective_query)
    invented_fields = asks_for_fabricated_schema_fields(effective_query)

    # ------------------------------------------------------------------
    # 4. Route
    # ------------------------------------------------------------------
    if forced_domain:
        domain = forced_domain
        route_result = None
    elif is_contractor_damage_query(effective_query):
        domain = "customer_support"
        route_result = None
    elif model_nums and any(w in effective_query.lower() for w in ("warranty", "troubleshoot", "model", "install")):
        domain = "customer_support"
        route_result = None
    else:
        from prism.core.embeddings import embed_one

        query_embedding = embed_one(retrieval_query)
        agnostic_hits = retrieve(retrieval_query, domain=None, top_k=10).chunks
        votes = score_by_hit_votes(agnostic_hits)
        route_result = route(query_embedding, hit_votes=votes, sticky_domain=session.active_domain)

        if route_result.ambiguous:
            candidates = sorted(route_result.scores.items(), key=lambda kv: -kv[1])[:2]
            candidate_domains = [c for c, _ in candidates]
            question = (
                "I want to make sure I point you to the right place -- is this "
                + " or ".join(CLARIFY_DOMAIN_LABELS.get(d, d) for d in candidate_domains)
                + "?"
            )
            from prism.core.memory import PendingClarification

            session.pending_clarification = PendingClarification(
                original_query=user_message, question=question, candidate_domains=candidate_domains
            )
            session.add_turn("assistant", question, domain=None)
            return TurnResult(
                session=session,
                reply_text=question,
                render_result=RenderResult(format="prose", content=question, mime_type="text/plain"),
                answer=None,
                domain=None,
                is_clarification=True,
                is_reformat=False,
            )
        domain = route_result.domain

    # ------------------------------------------------------------------
    # 5. Retrieve
    # ------------------------------------------------------------------
    result = _retrieve_for_query(retrieval_query, domain=domain, multi_domain=multi_domain)

    extra_notes: list[str] = []
    if leading:
        claimed = ", ".join(extract_claimed_inr_amounts(effective_query)) or "the user-stated amount"
        extra_notes.append(
            f"The user asserted {claimed} and asked for confirmation. Do NOT agree that this figure is correct "
            "unless it appears verbatim in the context. Cite the actual policy bands/limits from context and "
            "explicitly correct the user's figure if it does not match."
        )
    if false_premise:
        extra_notes.append(
            "The question embeds a false or loaded premise about selling/sharing personal data. "
            "Correct that premise first using privacy context before answering any follow-on mechanics."
        )
    if invented_fields:
        extra_notes.append(
            "The user asked for JSON fields that are NOT policy concepts: "
            + ", ".join(invented_fields)
            + ". Do not invent values for them — omit them, or set them to null / \"n/a\" / \"not in policy\"."
        )
    if is_contractor_damage_query(effective_query):
        extra_notes.append(
            "This is about contractor damage / warranty / liability. Prefer Assist warranty and support guidance. "
            "Do NOT answer with Bathroom Design Service pricing. For liability/compliance reporting, say the "
            "knowledge base does not establish contractor legal liability and you are not giving legal advice."
        )
    if multi_domain and ("terminat" in effective_query.lower() or "for cause" in effective_query.lower()):
        extra_notes.append(
            "For termination leave payout: distinguish CL (not encashable), SL (50% capped at 10 days), and EL "
            "(up to 30 days at separation). Do NOT invent a 'for cause = zero payout' or 'auto-delete data' rule. "
            "Privacy deletion requires a request unless context says otherwise. Expense claims: only state what "
            "Finance/HR context supports."
        )

    if model_nums and result.chunks:
        corpus = " ".join(c.text for c in result.chunks).upper()
        if not any(m.upper() in corpus for m in model_nums):
            answer = CanonicalAnswer(
                query=user_message,
                domain=domain or "customer_support",
                direct_answer=(
                    f"I couldn't find Kohler model {', '.join(model_nums)} in the support knowledge base. "
                    "I can't provide warranty or troubleshooting steps for an unknown model number."
                ),
                confidence="none",
                no_answer=True,
            )
        elif not result.chunks or not result.is_confident:
            answer = no_context_answer(user_message, domain or "unknown")
        else:
            answer = generate_answer(
                user_message,
                domain=domain or "customer_support",
                context_chunks=result.chunks,
                conversation_context=session.recent_context_str(4),
                multi_domain=multi_domain,
                extra_notes=extra_notes,
            )
    elif not result.chunks or not result.is_confident:
        answer = no_context_answer(user_message, domain or "unknown")
    else:
        answer = generate_answer(
            user_message,
            domain=domain,
            context_chunks=result.chunks,
            conversation_context=session.recent_context_str(4),
            multi_domain=multi_domain,
            extra_notes=extra_notes,
        )

    if answer.clarification_question and answer.no_answer:
        session.add_turn("assistant", answer.clarification_question, domain=domain)
        rr = render_format(answer, "prose")
        return TurnResult(
            session=session,
            reply_text=answer.clarification_question,
            render_result=rr,
            answer=answer,
            domain=domain,
            is_clarification=True,
            is_reformat=False,
        )

    return _commit_answer(session, answer=answer, domain=domain, chunks=result.chunks)


def _match_domain_from_reply(reply: str, candidates: list[str]) -> str | None:
    reply_l = reply.lower()
    for d in candidates:
        label = d.replace("_", " ")
        if label in reply_l or d in reply_l:
            return d
    if any(w in reply_l for w in ("first", "1", "one")) and candidates:
        return candidates[0]
    if any(w in reply_l for w in ("second", "2", "two")) and len(candidates) > 1:
        return candidates[1]
    return None
