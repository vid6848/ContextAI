"""State definition for ContextAI LangGraph agent."""

from typing import TypedDict, Annotated, Sequence
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
    context: dict
    messages: Annotated[Sequence[dict], operator.add]

