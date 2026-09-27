"""API routes for ContextAI."""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from src.backend.agent.graph import get_agent_app

router = APIRouter()

# Global compiled agent instance
_compiled_agent = None


def get_agent():
    """Retrieve or lazily initialize the compiled LangGraph agent."""
    global _compiled_agent
    if _compiled_agent is None:
        _compiled_agent = get_agent_app()
    return _compiled_agent


class ChatRequest(BaseModel):
    """Schema for incoming chat requests."""

    message: str = Field(..., min_length=1, description="The user query or message")
    user_id: str = Field(default="default_user", description="Identifier for the user")


class ChatResponse(BaseModel):
    """Schema for agent chat responses."""

    message: str
    intent: str
    confidence: float
    response: str


@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    """Endpoint for interacting with the ContextAI agent via LangGraph."""
    agent = get_agent()
    result = agent.invoke({"message": request.message, "user_id": request.user_id})

    return ChatResponse(
        message=result.get("message", request.message),
        intent=result.get("intent", "GENERAL"),
        confidence=float(result.get("confidence", 0.0)),
        response=result.get("response", ""),
    )

