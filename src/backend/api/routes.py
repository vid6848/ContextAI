"""API routes for ContextAI."""

import asyncio
import json
import logging
import os
import tempfile
import threading
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.backend.agent.graph import (
    get_agent_app,
    get_default_llm_client,
    get_default_rag_pipeline,
    get_default_sql_manager,
    get_default_vector_store,
)
from src.backend.core.config import settings
from src.backend.core.rate_limit import rate_limit
from src.backend.llm.client import LLMServiceUnavailableError
from src.backend.memory.sql_db import DEFAULT_CONVERSATION_TITLE
from src.backend.reminders.reminder_manager import ReminderManager

logger = logging.getLogger(__name__)

router = APIRouter()

# Anonymous browser ids are UUIDs; this also keeps ids safe to use in storage keys and filters.
USER_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
UPLOAD_READ_CHUNK = 1024 * 1024

chat_rate_limit = rate_limit("chat", lambda: settings.rate_limit_chat_per_minute)
upload_rate_limit = rate_limit("upload", lambda: settings.rate_limit_upload_per_minute)

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
    user_id: str = Field(default="default_user", pattern=USER_ID_PATTERN, description="Identifier for the user")
    conversation_id: str | None = Field(
        default=None, description="Existing conversation to continue; a new one is created when omitted"
    )
    replace_from_message_id: int | None = Field(
        default=None,
        description=(
            "Edit/regenerate: delete this user message and everything after it before answering `message`"
        ),
    )


class ChatResponse(BaseModel):
    """Schema for agent chat responses with optional agent execution details."""

    conversation_id: str
    message: str
    intent: str
    confidence: float
    response: str
    tool_used: str | None = None
    sources: list[dict[str, Any]] | None = None
    steps: list[dict[str, Any]] = []
    user_message_id: int | None = None
    assistant_message_id: int | None = None


class ClearMemoryRequest(BaseModel):
    """Schema for clearing user conversation memory."""

    user_id: str = Field(default="default_user", pattern=USER_ID_PATTERN, description="Identifier for the user")


class ConversationCreateRequest(BaseModel):
    """Schema for creating an empty conversation."""

    user_id: str = Field(default="default_user", pattern=USER_ID_PATTERN, description="Identifier for the user")
    title: str | None = Field(default=None, max_length=200)


class ConversationRenameRequest(BaseModel):
    """Schema for renaming a conversation."""

    title: str = Field(..., min_length=1, max_length=200)


class ReminderCreateRequest(BaseModel):
    """Schema for creating a new reminder."""

    reminder_text: str = Field(..., min_length=1, description="Text description of the reminder")
    scheduled_time: str = Field(..., min_length=1, description="Due or scheduled timestamp/string")
    user_id: str = Field(default="default_user", pattern=USER_ID_PATTERN, description="Identifier for the user")


# ============================================================================
# Conversation Endpoints
# ============================================================================

def _title_from_message(message: str) -> str:
    """Derive a short provisional title from the first user message."""
    clean = " ".join(message.split())
    return clean if len(clean) <= 60 else clean[:57].rstrip() + "…"


TITLE_PROMPT = (
    "Write a short title (2 to 6 words) for a chat that starts with the exchange below. "
    "Use sentence case, no quotes, no trailing punctuation. Reply with the title only."
)


def generate_title(user_message: str, answer: str) -> str | None:
    """Ask the LLM for a concise chat title; None if it fails or returns something unusable."""
    try:
        raw = get_default_llm_client().generate_response(
            message=[
                {"role": "system", "content": TITLE_PROMPT},
                {"role": "user", "content": f"User: {user_message[:1000]}\n\nAssistant: {answer[:1000]}"},
            ]
        )
    except Exception:
        logger.warning("Title generation failed", exc_info=True)
        return None
    title = (raw or "").strip().splitlines()[0].strip().strip("\"'*#").rstrip(".").strip() if raw else ""
    return title[:60] if 2 <= len(title) else None


def resolve_conversation(request: ChatRequest) -> dict[str, Any]:
    """Return the requested conversation (or create one titled after the message).

    For edit/regenerate requests, the targeted user message and everything after it are removed first,
    so the agent answers from the conversation as it stood before that message.
    """
    sql_mgr = get_default_sql_manager()
    user_id, conversation_id, message = request.user_id, request.conversation_id, request.message
    if conversation_id is None:
        if request.replace_from_message_id is not None:
            raise HTTPException(status_code=400, detail="replace_from_message_id requires a conversation_id.")
        return sql_mgr.create_conversation(user_id=user_id, title=_title_from_message(message))
    conversation = sql_mgr.get_conversation(conversation_id, user_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    if request.replace_from_message_id is not None:
        target = sql_mgr.get_message(request.replace_from_message_id, conversation_id, user_id)
        if target is None or target["role"] != "user":
            raise HTTPException(status_code=404, detail="Message to replace not found.")
        sql_mgr.delete_messages_from(request.replace_from_message_id, conversation_id, user_id)
    if conversation["title"] == DEFAULT_CONVERSATION_TITLE:
        sql_mgr.rename_conversation(conversation_id, user_id, _title_from_message(message))
    return conversation


@router.get("/conversations")
def list_conversations(user_id: str = Query(default="default_user", pattern=USER_ID_PATTERN)):
    """List a user's conversations, most recently active first."""
    return {"conversations": get_default_sql_manager().list_conversations(user_id)}


@router.post("/conversations", status_code=201)
def create_conversation(request: ConversationCreateRequest):
    """Create an empty conversation."""
    return get_default_sql_manager().create_conversation(user_id=request.user_id, title=request.title)


@router.get("/conversations/{conversation_id}/messages")
def get_conversation_messages(
    conversation_id: str,
    user_id: str = Query(default="default_user", pattern=USER_ID_PATTERN),
):
    """Return the full message history of a conversation."""
    sql_mgr = get_default_sql_manager()
    conversation = sql_mgr.get_conversation(conversation_id, user_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {
        "conversation": conversation,
        "messages": sql_mgr.get_conversation_messages(conversation_id, user_id),
    }


@router.patch("/conversations/{conversation_id}")
def rename_conversation(
    conversation_id: str,
    request: ConversationRenameRequest,
    user_id: str = Query(default="default_user", pattern=USER_ID_PATTERN),
):
    """Rename a conversation."""
    if not get_default_sql_manager().rename_conversation(conversation_id, user_id, request.title):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"success": True}


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, user_id: str = Query(default="default_user", pattern=USER_ID_PATTERN)):
    """Delete a conversation and all of its messages."""
    if not get_default_sql_manager().delete_conversation(conversation_id, user_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"success": True}


# ============================================================================
# Chat Endpoints
# ============================================================================

@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(chat_rate_limit)])
def chat_endpoint(request: ChatRequest):
    """Endpoint for interacting with the ContextAI agent via LangGraph."""
    conversation = resolve_conversation(request)
    agent = get_agent()
    try:
        result = agent.invoke(
            {"message": request.message, "user_id": request.user_id, "conversation_id": conversation["id"]}
        )
    except ValueError as err:
        # Configuration errors (e.g. missing API key) — return helpful message, not raw 500
        raise HTTPException(status_code=503, detail=str(err)) from err
    except LLMServiceUnavailableError as err:
        # Transient LLM unavailability after bounded retries/fallback
        raise HTTPException(status_code=503, detail=str(err)) from err
    except Exception as err:
        error_msg = str(err)
        # Check if the error or message indicates transient model unavailability
        if "temporarily unavailable" in error_msg.lower() or "503" in error_msg:
            raise HTTPException(
                status_code=503,
                detail="The AI model is temporarily unavailable. Please try again in a moment.",
            ) from err
        # Details stay in server logs; upstream errors can contain URLs, keys or internals
        logger.exception("Agent execution failed")
        raise HTTPException(
            status_code=502, detail="Something went wrong while generating a response. Please try again."
        ) from err

    return ChatResponse(
        conversation_id=conversation["id"],
        message=result.get("message", request.message),
        intent=result.get("intent", "GENERAL"),
        confidence=float(result.get("confidence", 0.0)),
        response=result.get("response", ""),
        tool_used=result.get("tool_name"),
        sources=result.get("rag_sources"),
        steps=result.get("steps") or [],
        user_message_id=result.get("user_message_id"),
        assistant_message_id=result.get("assistant_message_id"),
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _client_error_detail(err: Exception) -> str:
    """Map agent failures to a safe, user-facing message (details go to the logs)."""
    if isinstance(err, LLMServiceUnavailableError) or "temporarily unavailable" in str(err).lower():
        return "The AI model is temporarily unavailable. Please try again in a moment."
    if isinstance(err, ValueError):
        return str(err)
    logger.exception("Agent execution failed", exc_info=err)
    return "Something went wrong while generating a response. Please try again."


@router.post("/chat/stream", dependencies=[Depends(chat_rate_limit)])
async def chat_stream_endpoint(request: ChatRequest):
    """Stream the agent's work as Server-Sent Events.

    Events: `meta` (conversation id) → `step` (memory/intent/tool progress) → `token` (response text
    deltas) → `done` (intent, tool, sources, saved message ids) or `error`; a new chat then gets a
    `title` event with an LLM-written title. If the client disconnects
    (Stop button), generation is cancelled and the partial answer is saved.
    """
    conversation = resolve_conversation(request)
    agent = get_agent()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    cancel_event = threading.Event()

    def publish(event: dict[str, Any] | None) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, event)

    def run_agent() -> None:
        final: dict[str, Any] = {}
        try:
            for mode, chunk in agent.stream(
                {"message": request.message, "user_id": request.user_id, "conversation_id": conversation["id"]},
                stream_mode=["custom", "values"],
                config={"configurable": {"stream": True, "cancel_event": cancel_event}},
            ):
                if mode == "custom":
                    publish(chunk)
                else:
                    final = chunk
            publish({
                "type": "done",
                "intent": final.get("intent", "GENERAL"),
                "confidence": float(final.get("confidence", 0.0)),
                "tool_used": final.get("tool_name"),
                "sources": final.get("rag_sources"),
                "stopped": bool(final.get("stopped")),
                "user_message_id": final.get("user_message_id"),
                "assistant_message_id": final.get("assistant_message_id"),
            })
            # A brand-new chat gets a proper title once the first answer exists
            if request.conversation_id is None and final.get("response") and not final.get("stopped"):
                title = generate_title(request.message, final["response"])
                if title and get_default_sql_manager().rename_conversation(conversation["id"], request.user_id, title):
                    publish({"type": "title", "title": title})
        except Exception as err:
            publish({"type": "error", "detail": _client_error_detail(err)})
        finally:
            publish(None)

    async def events():
        yield _sse("meta", {"conversation_id": conversation["id"], "title": conversation["title"]})
        loop.run_in_executor(None, run_agent)
        try:
            while (event := await queue.get()) is not None:
                yield _sse(event.pop("type"), event)
        finally:
            # Runs on normal completion and when the client disconnects mid-stream (Stop button): the
            # worker thread sees the event, stops reading from the model and saves the partial answer.
            cancel_event.set()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ============================================================================
# Memory Management Endpoints
# ============================================================================

@router.post("/memory/clear")
def clear_memory_endpoint(request: ClearMemoryRequest):
    """Clear conversations, history and long-term semantic memories for the specified user."""
    get_default_sql_manager().clear_history(user_id=request.user_id)
    get_default_vector_store().delete_user_memories(user_id=request.user_id)
    return {"success": True, "message": "Your conversations and memories have been cleared."}


# ============================================================================
# Document / RAG Endpoints
# ============================================================================

@router.post("/documents/upload", dependencies=[Depends(upload_rate_limit)])
async def upload_document(
    file: UploadFile = File(...),
    user_id: str = Query(default="default_user", pattern=USER_ID_PATTERN),
):
    """Upload and index a PDF into the user's private document collection."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    size = 0
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp_path = tmp.name
        # Stream to disk in chunks so a huge upload can't exhaust memory
        while chunk := await file.read(UPLOAD_READ_CHUNK):
            size += len(chunk)
            if size > max_bytes:
                break
            tmp.write(chunk)

    try:
        if size > max_bytes:
            raise HTTPException(status_code=413, detail=f"PDF is larger than {settings.max_upload_mb} MB.")
        if size == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
        with open(tmp_path, "rb") as fh:
            if fh.read(5) != b"%PDF-":
                raise HTTPException(status_code=400, detail="File is not a valid PDF.")

        pipeline = get_default_rag_pipeline()
        res = pipeline.ingest_pdf(tmp_path, user_id=user_id, document_name=os.path.basename(file.filename))
        if not res.get("success"):
            raise HTTPException(status_code=422, detail=res.get("error", "PDF ingestion failed."))

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
def get_documents_status(user_id: str = Query(default="default_user", pattern=USER_ID_PATTERN)):
    """Retrieve the user's document index statistics."""
    pipeline = get_default_rag_pipeline()
    return {
        "success": True,
        "total_chunks": pipeline.count(user_id),
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
        raise HTTPException(status_code=400, detail=str(err)) from err


@router.get("/reminders")
def get_reminders(
    user_id: str = Query(default="default_user", pattern=USER_ID_PATTERN),
    status: str | None = Query(default=None),
):
    """Retrieve all reminders for a user."""
    mgr = get_reminder_manager()
    reminders = mgr.get_reminders(user_id=user_id, status=status)
    return {"success": True, "reminders": reminders}


@router.patch("/reminders/{reminder_id}/complete")
def complete_reminder(reminder_id: int, user_id: str = Query(default="default_user", pattern=USER_ID_PATTERN)):
    """Mark a reminder as completed."""
    mgr = get_reminder_manager()
    updated = mgr.complete_reminder(reminder_id=reminder_id, user_id=user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Reminder not found.")
    return {"success": True, "message": "Reminder marked as completed."}


@router.delete("/reminders/{reminder_id}")
def delete_reminder(reminder_id: int, user_id: str = Query(default="default_user", pattern=USER_ID_PATTERN)):
    """Delete a reminder by ID."""
    mgr = get_reminder_manager()
    deleted = mgr.delete_reminder(reminder_id=reminder_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Reminder not found.")
    return {"success": True, "message": "Reminder deleted."}
