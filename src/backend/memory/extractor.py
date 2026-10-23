"""LLM-based long-term memory: extract durable facts about the user and reconcile them with what's stored."""

import json
import logging
import re
from typing import Any

from src.backend.llm.client import LLMClient
from src.backend.memory.vector_store import ChromaMemoryStore

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """You maintain the long-term memory of a personal assistant.

From the user's latest message, find durable facts about the user that will still matter in future
conversations: name, where they live, work or study, preferences (tools, languages, style of answers),
goals, important dates, people and pets in their life, and constraints such as allergies or accessibility needs.

Ignore questions, one-off requests, small talk, opinions about the current topic, and facts about the world.

Compare with the existing memories and reply with JSON only:
{"operations": [{"op": "add", "fact": "..."}, {"op": "update", "id": "<existing id>", "fact": "..."},
                {"op": "delete", "id": "<existing id>"}]}

Rules:
- Write each fact as a short third-person statement, e.g. "Prefers answers with Python examples".
- Use "update" when the message changes an existing fact (e.g. a move: "Lives in Berlin (moved from Pune)").
- Use "delete" when the user asks you to forget something.
- Never add a fact that an existing memory already says.
- If nothing qualifies, reply {"operations": []}."""

# Only messages that talk about the user (or ask to remember/forget) are worth an LLM call
_SELF_REFERENCE = re.compile(r"\b(i|i'm|im|i've|i'd|my|me|mine|myself|we|our|remember|forget)\b", re.IGNORECASE)


def worth_checking(message: str) -> bool:
    """Cheap pre-filter so "what's the weather in Tokyo?" never costs an extraction call."""
    return len(message.split()) >= 3 and bool(_SELF_REFERENCE.search(message))


def _parse_operations(raw: str) -> list[dict[str, Any]]:
    ops = _parse_json(raw).get("operations")
    return ops if isinstance(ops, list) else []


TITLE_PROMPT = (
    "Write a short title (2 to 6 words) for a chat that starts with the exchange below. "
    "Use sentence case, no quotes, no trailing punctuation. Reply with the title only."
)
TITLE_ADDENDUM = (
    '\n\nAlso include "title": a 2-6 word sentence-case title (no quotes or trailing punctuation) for a chat '
    'that starts with this message, e.g. {"title": "Weekend trip ideas", "operations": []}.'
)


def needs_llm_title(message: str) -> bool:
    """Short first messages ("What's the weather in Tokyo?") already make a good title."""
    return len(message.split()) > 6


def clean_title(raw: str | None) -> str | None:
    lines = (raw or "").strip().splitlines()
    title = lines[0].strip().strip("\"'*#").rstrip(".").strip() if lines else ""
    return title[:60] if len(title) >= 2 else None


def _parse_json(raw: str) -> dict[str, Any]:
    found = re.search(r"\{.*\}", raw.strip(), re.DOTALL)
    if not found:
        return {}
    try:
        data = json.loads(found.group(0))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def post_turn(
    llm: LLMClient,
    store: ChromaMemoryStore,
    user_id: str,
    message: str,
    answer: str = "",
    *,
    want_title: bool = False,
    want_memory: bool = True,
) -> dict[str, Any]:
    """After a reply: update long-term memory and/or title a new chat, in at most ONE model call.

    Returns {"changes": [{"op", "id", "fact"}], "title": str | None}. Failures are logged and swallowed:
    neither must ever break a chat turn.
    """
    want_memory = want_memory and worth_checking(message)
    if not (want_memory or want_title):
        return {"changes": [], "title": None}
    related: list[dict[str, Any]] = []
    try:
        if want_memory:
            related = store.search_memories(message, user_id=user_id, limit=6)
            existing = "\n".join(f"- [{m['id']}] {m['memory']}" for m in related) or "(none)"
            prompt = [
                {"role": "system", "content": EXTRACTION_PROMPT + (TITLE_ADDENDUM if want_title else "")},
                {"role": "user", "content": f"Existing memories:\n{existing}\n\nUser's latest message:\n{message}"},
            ]
        else:
            prompt = [
                {"role": "system", "content": TITLE_PROMPT},
                {"role": "user", "content": f"User: {message[:1000]}\n\nAssistant: {answer[:1000]}"},
            ]
        raw = llm.generate_response(message=prompt)
    except Exception:
        logger.warning("Post-turn update failed", exc_info=True)
        return {"changes": [], "title": None}

    if not want_memory:
        return {"changes": [], "title": clean_title(raw)}
    data = _parse_json(raw)
    title = clean_title(str(data.get("title") or "")) if want_title else None
    ops = data.get("operations") if isinstance(data.get("operations"), list) else []
    return {"changes": _apply(store, user_id, ops, related), "title": title}


def update_long_term_memory(
    llm: LLMClient, store: ChromaMemoryStore, user_id: str, message: str
) -> list[dict[str, Any]]:
    """Extract facts from the user's message and apply add/update/delete operations (memory only)."""
    return post_turn(llm, store, user_id, message, want_memory=True)["changes"]


def _apply(
    store: ChromaMemoryStore, user_id: str, ops: list[Any], related: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Apply the model's operations, only touching memories it was shown (so only the user's own)."""
    known = {m["id"]: m["memory"] for m in related}
    applied: list[dict[str, Any]] = []
    for op in ops[:5]:
        if not isinstance(op, dict):
            continue
        kind, fact, mid = op.get("op"), str(op.get("fact") or "").strip()[:300], op.get("id")
        try:
            if kind == "add" and fact and fact not in known.values():
                applied.append({"op": "add", "id": store.add_memory(fact, user_id, {"source": "chat"}), "fact": fact})
            elif kind == "update" and fact and mid in known and store.update_memory(mid, user_id, fact):
                applied.append({"op": "update", "id": mid, "fact": fact})
            elif kind == "delete" and mid in known and store.delete_memory(mid, user_id):
                applied.append({"op": "delete", "id": mid, "fact": known[mid]})
        except Exception:
            logger.warning("Applying memory operation failed", exc_info=True)
    return applied
