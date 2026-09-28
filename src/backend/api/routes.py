"""API routes for ContextAI."""

import os
import tempfile
from typing import Any
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from src.backend.agent.graph import (
    get_agent_app,
    get_default_rag_pipeline,
    get_default_sql_manager,
)
from src.backend.llm.client import LLMServiceUnavailableError
from src.backend.reminders.reminder_manager import ReminderManager

router = APIRouter()

# Global compiled agent instance
_compiled_agent = None
_default_reminder_manager: ReminderManager | None = None


def get_agent():
    """Retrieve or lazily initialize the compiled LangGraph agent."""
    global _compiled_agent
    if _compiled_agent is None:
        _compiled_agent = get_agent_app()
    return _compiled_agent


def get_reminder_manager() -> ReminderManager:
    """Retrieve or lazily initialize singleton ReminderManager."""
    global _default_reminder_manager
    if _default_reminder_manager is None:
        _default_reminder_manager = ReminderManager()
    return _default_reminder_manager


# ============================================================================
# Schemas
# ============================================================================

class ChatRequest(BaseModel):
    """Schema for incoming chat requests."""

    message: str = Field(..., min_length=1, description="The user query or message")
    user_id: str = Field(default="default_user", description="Identifier for the user")


class ChatResponse(BaseModel):
    """Schema for agent chat responses with optional agent execution details."""

    message: str
    intent: str
    confidence: float
    response: str
    tool_used: str | None = None
    sources: list[dict[str, Any]] | None = None


class ClearMemoryRequest(BaseModel):
    """Schema for clearing user conversation memory."""

    user_id: str = Field(default="default_user", description="Identifier for the user")


class ReminderCreateRequest(BaseModel):
    """Schema for creating a new reminder."""

    reminder_text: str = Field(..., min_length=1, description="Text description of the reminder")
    scheduled_time: str = Field(..., min_length=1, description="Due or scheduled timestamp/string")
    user_id: str = Field(default="default_user", description="Identifier for the user")


# ============================================================================
# Chat Endpoints
# ============================================================================

@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    """Endpoint for interacting with the ContextAI agent via LangGraph."""
    agent = get_agent()
    try:
        result = agent.invoke({"message": request.message, "user_id": request.user_id})
    except ValueError as err:
        # Configuration errors (e.g. missing API key) — return helpful message, not raw 500
        raise HTTPException(status_code=503, detail=str(err))
    except LLMServiceUnavailableError as err:
        # Transient LLM unavailability after bounded retries/fallback
        raise HTTPException(status_code=503, detail=str(err))
    except Exception as err:
        error_msg = str(err)
        # Check if the error or message indicates transient model unavailability
        if "temporarily unavailable" in error_msg.lower() or "503" in error_msg:
            raise HTTPException(
                status_code=503,
                detail="Gemini is temporarily unavailable. Please try again in a moment.",
            )
        # Never expose raw API keys in error messages
        if "api_key" in error_msg.lower():
            error_msg = "LLM service configuration error. Check server logs for details."
        raise HTTPException(status_code=502, detail=f"Agent execution error: {error_msg}")

    return ChatResponse(
        message=result.get("message", request.message),
        intent=result.get("intent", "GENERAL"),
        confidence=float(result.get("confidence", 0.0)),
        response=result.get("response", ""),
        tool_used=result.get("tool_name"),
        sources=result.get("rag_sources"),
    )


# ============================================================================
# Memory Management Endpoints
# ============================================================================

@router.post("/memory/clear")
def clear_memory_endpoint(request: ClearMemoryRequest):
    """Clear conversation history for the specified user."""
    sql_mgr = get_default_sql_manager()
    sql_mgr.clear_history(user_id=request.user_id)
    return {"success": True, "message": f"Conversation history cleared for {request.user_id}."}


# ============================================================================
# Document / RAG Endpoints
# ============================================================================

@router.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload and index a PDF document into ChromaDB document RAG collection."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        pipeline = get_default_rag_pipeline()
        res = pipeline.ingest_pdf(tmp_path)
        if not res.get("success"):
            raise HTTPException(status_code=500, detail=res.get("error", "PDF ingestion failed."))

        return {
            "success": True,
            "document_name": file.filename,
            "total_pages": res.get("total_pages", 0),
            "total_chunks": res.get("total_chunks", 0),
        }
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.get("/documents")
def get_documents_status():
    """Retrieve document index statistics."""
    pipeline = get_default_rag_pipeline()
    return {
        "success": True,
        "total_chunks": pipeline.count(),
    }


# ============================================================================
# Reminder Endpoints
# ============================================================================

@router.post("/reminders")
def create_reminder(request: ReminderCreateRequest):
    """Create a new reminder for a user."""
    mgr = get_reminder_manager()
    try:
        reminder = mgr.create_reminder(
            user_id=request.user_id,
            reminder_text=request.reminder_text,
            scheduled_time=request.scheduled_time,
        )
        return {"success": True, "reminder": reminder}
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@router.get("/reminders")
def get_reminders(
    user_id: str = Query(default="default_user"),
    status: str | None = Query(default=None),
):
    """Retrieve all reminders for a user."""
    mgr = get_reminder_manager()
    reminders = mgr.get_reminders(user_id=user_id, status=status)
    return {"success": True, "reminders": reminders}


@router.patch("/reminders/{reminder_id}/complete")
def complete_reminder(reminder_id: int, user_id: str = Query(default="default_user")):
    """Mark a reminder as completed."""
    mgr = get_reminder_manager()
    updated = mgr.complete_reminder(reminder_id=reminder_id, user_id=user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Reminder not found.")
    return {"success": True, "message": "Reminder marked as completed."}


@router.delete("/reminders/{reminder_id}")
def delete_reminder(reminder_id: int, user_id: str = Query(default="default_user")):
    """Delete a reminder by ID."""
    mgr = get_reminder_manager()
    deleted = mgr.delete_reminder(reminder_id=reminder_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Reminder not found.")
    return {"success": True, "message": "Reminder deleted."}
