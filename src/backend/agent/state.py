"""State definition for ContextAI LangGraph agent."""

from typing import TypedDict, Annotated, Sequence, Any
import operator


class AgentState(TypedDict, total=False):
    """State definition for LangGraph workflow."""

    message: str
    user_id: str
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
