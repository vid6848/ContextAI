"""State definition for ContextAI LangGraph agent."""

import operator
from collections.abc import Sequence
from typing import Annotated, Any, TypedDict


class AgentState(TypedDict, total=False):
    """State definition for LangGraph workflow."""

    message: str
    user_id: str
    conversation_id: str
    # Names of PDFs attached to this message; routes to document search over just those files
    attachments: list[str]
    intent: str
    current_intent: str
    confidence: float
    response: str
    final_response: str
    context: dict[str, Any]
    conversation_history: list[dict[str, Any]]
    semantic_memories: list[str]
    tool_name: str
    tool_result: dict[str, Any]
    document_chunks: list[dict[str, Any]]
    rag_sources: list[dict[str, Any]]
    messages: Annotated[Sequence[dict], operator.add]
    # Timed agent steps (memory recall, routing, tool calls) shown in the UI and stored with the answer
    steps: Annotated[list[dict[str, Any]], operator.add]
    stopped: bool
    # "classifier" (fixed tool path) or "llm" (function calling), decided by the router
    route: str
    # UI cards from tool results ({tool: weather|crypto, output}); several when the LLM chains tools
    cards: list[dict[str, Any]]
    tools_used: list[str]
    user_message_id: int
    assistant_message_id: int
