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
    text = raw.strip()
    fenced = re.search(r"\{.*\}", text, re.DOTALL)
    if not fenced:
        return []
    try:
        data = json.loads(fenced.group(0))
    except json.JSONDecodeError:
        return []
    ops = data.get("operations") if isinstance(data, dict) else None
    return ops if isinstance(ops, list) else []


def update_long_term_memory(
    llm: LLMClient, store: ChromaMemoryStore, user_id: str, message: str
) -> list[dict[str, Any]]:
    """Extract facts from the user's message and apply add/update/delete operations.

    Returns the applied changes as [{"op", "id", "fact"}], for the UI's "Memory updated" note.
    Failures are logged and swallowed: memory must never break a chat turn.
    """
    if not worth_checking(message):
        return []
    try:
        related = store.search_memories(message, user_id=user_id, limit=6)
        existing = "\n".join(f"- [{m['id']}] {m['memory']}" for m in related) or "(none)"
        raw = llm.generate_response(
            message=[
                {"role": "system", "content": EXTRACTION_PROMPT},
                {"role": "user", "content": f"Existing memories:\n{existing}\n\nUser's latest message:\n{message}"},
            ]
        )
    except Exception:
        logger.warning("Memory extraction failed", exc_info=True)
        return []

    known = {m["id"]: m["memory"] for m in related}
    applied: list[dict[str, Any]] = []
    for op in _parse_operations(raw)[:5]:
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
