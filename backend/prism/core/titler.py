"""Session auto-titling (Piece 2c).

One lightweight call on the first exchange using the small TITLE_MODEL
(qwen2.5:3b-instruct) -- not the main generation model -- since this is a
cheap summarization task, not reasoning, and shouldn't compete for the same
latency/VRAM budget as real answers. Not called per-turn; only once at
session start, plus optionally once more if the topic shifts domain later.
"""

from __future__ import annotations

from prism.core.config import TITLE_MODEL
from prism.core.ollama_client import get_ollama_client, keep_alive_value

TITLE_SYSTEM_PROMPT = (
    "Generate a short, descriptive chat title (max 6 words, no quotes, no trailing punctuation, no JSON). "
    "Summarize what the user is asking about. Output ONLY the title text."
)


def _sanitize_title(title: str, fallback_message: str) -> str:
    t = title.strip().strip('"').strip("'").strip()
    if t.startswith("{") or t.startswith("[") or '"risk_level"' in t or "entitlement_days" in t:
        words = [w for w in fallback_message.replace("?", "").split() if w][:6]
        return " ".join(words) if words else "New conversation"
    if "generate short descriptive" in t.lower() or "output only" in t.lower():
        words = [w for w in fallback_message.replace("?", "").split() if w][:6]
        return " ".join(words) if words else "New conversation"
    words = t.split()
    if len(words) > 8:
        t = " ".join(words[:8])
    return t or "New conversation"


def generate_title(first_user_message: str) -> str:
    resp = get_ollama_client().chat(
        model=TITLE_MODEL,
        messages=[
            {"role": "system", "content": TITLE_SYSTEM_PROMPT},
            {"role": "user", "content": first_user_message[:500]},
        ],
        options={"temperature": 0.3, "num_predict": 20},
        keep_alive=keep_alive_value(),
    )
    return _sanitize_title(resp["message"]["content"], first_user_message)


def maybe_retitle(*, current_title: str | None, new_domain: str, first_message_of_new_domain: str) -> str | None:
    """Optionally regenerate the title if the conversation has clearly moved
    to a new domain and the current title doesn't reflect it. Cheap heuristic
    gate (domain name not mentioned in title) avoids calling the LLM on every
    domain switch."""
    if not current_title:
        return generate_title(first_message_of_new_domain)
    domain_words = new_domain.replace("_", " ").split()
    if any(w.lower() in current_title.lower() for w in domain_words):
        return None
    return generate_title(first_message_of_new_domain)
