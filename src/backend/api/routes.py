"""API routes for ContextAI."""

import asyncio
import json
import logging
import os
import tempfile
import threading
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.backend.agent.graph import (
    answer_cards,
    get_agent_app,
    get_default_rag_pipeline,
    get_default_sql_manager,
    get_default_utility_llm,
    get_default_vector_store,
    tool_card,
)
from src.backend.auth import ACCOUNT_PREFIX, USER_ID_PATTERN, bearer_account, current_user_id, resolve_user
from src.backend.core import tracing
from src.backend.core.config import settings
from src.backend.core.rate_limit import rate_limit
from src.backend.db.embeddings import release_memory
from src.backend.llm.client import LLMServiceUnavailableError
from src.backend.memory.extractor import needs_llm_title, post_turn
from src.backend.memory.sql_db import DEFAULT_CONVERSATION_TITLE
from src.backend.reminders.push import PushService
from src.backend.reminders.reminder_manager import ReminderManager
from src.backend.reminders.timeparse import parse_when

logger = logging.getLogger(__name__)

router = APIRouter()

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
    timezone: str | None = Field(
        default=None, max_length=64, description="User's IANA timezone, for dates and reminders"
    )
    attachments: list[Annotated[str, Field(min_length=1, max_length=255)]] = Field(
        default_factory=list, max_length=5, description="Names of uploaded PDFs this message is about"
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


class FeedbackRequest(BaseModel):
    """Thumbs up/down on an assistant answer; null clears it."""

    rating: Literal["up", "down"] | None = None


class ReminderCreateRequest(BaseModel):
    """Schema for creating a new reminder."""

    reminder_text: str = Field(..., min_length=1, description="Text description of the reminder")
    scheduled_time: str = Field(
        ..., min_length=1, max_length=120, description='When: ISO timestamp or natural language ("tomorrow at 5pm")'
    )
    timezone: str | None = Field(default=None, max_length=64, description="IANA timezone, e.g. Asia/Kolkata")
    user_id: str = Field(default="default_user", pattern=USER_ID_PATTERN, description="Identifier for the user")


# ============================================================================
# Conversation Endpoints
# ============================================================================

def _title_from_message(message: str) -> str:
    """Derive a short provisional title from the first user message."""
    clean = " ".join(message.split())
    return clean if len(clean) <= 60 else clean[:57].rstrip() + "…"


def _agent_input(request: ChatRequest, conversation: dict[str, Any]) -> dict[str, Any]:
    return {
        "message": request.message,
        "user_id": request.user_id,
        "conversation_id": conversation["id"],
        "attachments": request.attachments,
        "timezone": request.timezone,
    }


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
def list_conversations(user_id: str = Depends(current_user_id)):
    """List a user's conversations, most recently active first."""
    return {"conversations": get_default_sql_manager().list_conversations(user_id)}


@router.post("/conversations", status_code=201)
def create_conversation(request: ConversationCreateRequest, account: str | None = Depends(bearer_account)):
    """Create an empty conversation."""
    request.user_id = resolve_user(account, request.user_id)
    return get_default_sql_manager().create_conversation(user_id=request.user_id, title=request.title)


@router.get("/conversations/{conversation_id}/messages")
def get_conversation_messages(
    conversation_id: str,
    user_id: str = Depends(current_user_id),
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


@router.put("/conversations/{conversation_id}/messages/{message_id}/feedback")
def set_message_feedback(
    conversation_id: str,
    message_id: int,
    request: FeedbackRequest,
    user_id: str = Depends(current_user_id),
):
    """Record 👍/👎 feedback on an assistant answer."""
    sql_mgr = get_default_sql_manager()
    message = sql_mgr.get_message(message_id, conversation_id, user_id)
    if message is None or message["role"] != "assistant":
        raise HTTPException(status_code=404, detail="Message not found.")
    sql_mgr.update_message_metadata(message_id, conversation_id, user_id, {"feedback": request.rating})
    tracing.score_feedback((message.get("metadata") or {}).get("trace_id"), request.rating)
    return {"success": True, "rating": request.rating}


@router.patch("/conversations/{conversation_id}")
def rename_conversation(
    conversation_id: str,
    request: ConversationRenameRequest,
    user_id: str = Depends(current_user_id),
):
    """Rename a conversation."""
    if not get_default_sql_manager().rename_conversation(conversation_id, user_id, request.title):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"success": True}


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, user_id: str = Depends(current_user_id)):
    """Delete a conversation and all of its messages."""
    if not get_default_sql_manager().delete_conversation(conversation_id, user_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"success": True}


# ============================================================================
# Chat Endpoints
# ============================================================================

def after_reply(request: ChatRequest, final: dict[str, Any]) -> dict[str, Any]:
    """Side tasks once the reply exists: update long-term memory and title a new chat (one utility call).

    Returns {"changes": [...], "title": str | None}; both are persisted here.
    """
    if not final.get("response") or final.get("stopped"):
        return {"changes": [], "title": None}
    result = post_turn(
        get_default_utility_llm(),
        get_default_vector_store(),
        request.user_id,
        request.message,
        final["response"],
        want_title=request.conversation_id is None and needs_llm_title(request.message),
        want_memory=settings.memory_mode == "llm",
    )
    sql = get_default_sql_manager()
    conversation_id = final.get("conversation_id")
    if result["changes"] and final.get("assistant_message_id") and conversation_id:
        sql.update_message_metadata(
            final["assistant_message_id"], conversation_id, request.user_id, {"memory": result["changes"]}
        )
    renamed = result["title"] and conversation_id and sql.rename_conversation(
        conversation_id, request.user_id, result["title"]
    )
    if not renamed:
        result["title"] = None
    return result


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(chat_rate_limit)])
def chat_endpoint(
    request: ChatRequest, background: BackgroundTasks, account: str | None = Depends(bearer_account)
):
    """Endpoint for interacting with the ContextAI agent via LangGraph."""
    request.user_id = resolve_user(account, request.user_id)
    conversation = resolve_conversation(request)
    agent = get_agent()
    try:
        with tracing.turn(request.user_id, conversation["id"], request.message) as trace:
            result = agent.invoke(_agent_input(request, conversation))
            trace.update(output=result.get("response"))
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

    background.add_task(after_reply, request, result)
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
async def chat_stream_endpoint(request: ChatRequest, account: str | None = Depends(bearer_account)):
    """Stream the agent's work as Server-Sent Events.

    Events: `meta` (conversation id) → `step` (memory/intent/tool progress) → `token` (response text
    deltas) → `done` (intent, tool, sources, saved message ids) or `error`; a new chat then gets a
    `title` event with an LLM-written title. If the client disconnects
    (Stop button), generation is cancelled and the partial answer is saved.
    """
    request.user_id = resolve_user(account, request.user_id)
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
            with tracing.turn(request.user_id, conversation["id"], request.message) as trace:
                for mode, chunk in agent.stream(
                    _agent_input(request, conversation),
                    stream_mode=["custom", "values"],
                    config={"configurable": {"stream": True, "cancel_event": cancel_event}},
                ):
                    if mode == "custom":
                        publish(chunk)
                    else:
                        final = chunk
                trace.update(output=final.get("response"), metadata={"stopped": bool(final.get("stopped"))})
                publish({
                    "type": "done",
                    "intent": final.get("intent", "GENERAL"),
                    "confidence": float(final.get("confidence", 0.0)),
                    "tool_used": final.get("tool_name"),
                    "sources": final.get("rag_sources"),
                    "tool_output": tool_card(final),
                    "cards": answer_cards(final),
                    "tools_used": final.get("tools_used") or ([final["tool_name"]] if final.get("tool_name") else []),
                    "stopped": bool(final.get("stopped")),
                    "user_message_id": final.get("user_message_id"),
                    "assistant_message_id": final.get("assistant_message_id"),
                })
                extra = after_reply(request, final)
                if extra["changes"]:
                    publish({"type": "memory", "changes": extra["changes"]})
                if extra["title"]:
                    publish({"type": "title", "title": extra["title"]})
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
def clear_memory_endpoint(request: ClearMemoryRequest, account: str | None = Depends(bearer_account)):
    """Clear conversations, history and long-term semantic memories for the specified user."""
    request.user_id = resolve_user(account, request.user_id)
    get_default_sql_manager().clear_history(user_id=request.user_id)
    get_default_vector_store().delete_user_memories(user_id=request.user_id)
    return {"success": True, "message": "Your conversations and memories have been cleared."}


class MemoryRequest(BaseModel):
    """A fact to add, or the new text of an existing memory."""

    fact: str = Field(..., min_length=1, max_length=300)


@router.get("/memories")
def list_memories(user_id: str = Depends(current_user_id)):
    """Everything ContextAI remembers about the user."""
    return {"memories": get_default_vector_store().list_memories(user_id)}


@router.post("/memories", status_code=201)
def add_memory(request: MemoryRequest, user_id: str = Depends(current_user_id)):
    """Teach ContextAI a fact directly."""
    memory_id = get_default_vector_store().add_memory(request.fact.strip(), user_id, {"source": "manual"})
    return {"id": memory_id, "fact": request.fact.strip()}


@router.patch("/memories/{memory_id}")
def edit_memory(
    memory_id: str, request: MemoryRequest, user_id: str = Depends(current_user_id)
):
    """Correct a memory."""
    if not get_default_vector_store().update_memory(memory_id, user_id, request.fact.strip()):
        raise HTTPException(status_code=404, detail="Memory not found.")
    return {"success": True}


@router.delete("/memories/{memory_id}")
def forget_memory(memory_id: str, user_id: str = Depends(current_user_id)):
    """Forget one memory."""
    if not get_default_vector_store().delete_memory(memory_id, user_id):
        raise HTTPException(status_code=404, detail="Memory not found.")
    return {"success": True}


@router.delete("/memories")
def forget_all_memories(user_id: str = Depends(current_user_id)):
    """Forget everything about the user (chats are kept)."""
    get_default_vector_store().delete_user_memories(user_id)
    return {"success": True}


# ============================================================================
# Document / RAG Endpoints
# ============================================================================

@router.post("/documents/upload", dependencies=[Depends(upload_rate_limit)])
async def upload_document(
    file: UploadFile = File(...),
    user_id: str = Depends(current_user_id),
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
        # In a worker thread, so parsing and embedding a big PDF doesn't stall every other request
        res = await run_in_threadpool(
            pipeline.ingest_pdf, tmp_path, user_id=user_id, document_name=os.path.basename(file.filename)
        )
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
        release_memory()


@router.get("/documents")
def get_documents_status(user_id: str = Depends(current_user_id)):
    """List the user's documents and the total number of indexed passages."""
    pipeline = get_default_rag_pipeline()
    return {
        "success": True,
        "total_chunks": pipeline.count(user_id),
        "documents": pipeline.list_documents(user_id),
    }


@router.delete("/documents/{document_id}")
def delete_document(document_id: str, user_id: str = Depends(current_user_id)):
    """Delete one of the user's documents and all of its passages."""
    if not get_default_rag_pipeline().delete_document(user_id, document_id):
        raise HTTPException(status_code=404, detail="Document not found.")
    return {"success": True}


# ============================================================================
# Reminder Endpoints
# ============================================================================

@router.post("/reminders")
def create_reminder(request: ReminderCreateRequest, account: str | None = Depends(bearer_account)):
    """Create a new reminder for a user."""
    request.user_id = resolve_user(account, request.user_id)
    mgr = get_reminder_manager()
    try:
        reminder = mgr.create_reminder(
            user_id=request.user_id,
            reminder_text=request.reminder_text,
            scheduled_time=request.scheduled_time,
            timezone=request.timezone,
        )
        return {"success": True, "reminder": reminder}
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@router.get("/reminders")
def get_reminders(
    user_id: str = Depends(current_user_id),
    status: str | None = Query(default=None),
):
    """Retrieve all reminders for a user."""
    mgr = get_reminder_manager()
    reminders = mgr.get_reminders(user_id=user_id, status=status)
    return {"success": True, "reminders": reminders}


# ============================================================================
# Accounts
# ============================================================================

class ClaimRequest(BaseModel):
    """The browser's guest id, whose data should move into the signed-in account."""

    guest_id: str = Field(..., pattern=USER_ID_PATTERN)


@router.get("/config")
def public_config():
    """What the web app needs to offer sign-in (all public values)."""
    if not (settings.supabase_url and settings.supabase_publishable_key):
        return {"auth": None}
    return {
        "auth": {
            "supabase_url": settings.supabase_url,
            "publishable_key": settings.supabase_publishable_key,
            "required": settings.auth_required,
        }
    }


@router.post("/auth/claim")
def claim_guest_data(request: ClaimRequest, account: str | None = Depends(bearer_account)):
    """After sign-in, move this browser's guest chats, memories, documents and reminders into the account."""
    if account is None:
        raise HTTPException(status_code=401, detail="Sign in first.")
    if request.guest_id.startswith(ACCOUNT_PREFIX) or request.guest_id == account:
        raise HTTPException(status_code=400, detail="That isn't a guest id.")
    moved = {
        "conversations": get_default_sql_manager().reassign_user(request.guest_id, account),
        "memories": get_default_vector_store().reassign_user(request.guest_id, account),
        "document_passages": get_default_rag_pipeline().reassign_user(request.guest_id, account),
        "reminders": get_reminder_manager().reassign_user(request.guest_id, account),
        "push_subscriptions": get_push_service().reassign_user(request.guest_id, account),
    }
    return {"success": True, "user_id": account, "moved": moved}


_push_service: PushService | None = None


def get_push_service() -> PushService:
    global _push_service
    if _push_service is None:
        _push_service = PushService(reminders=get_reminder_manager())
    return _push_service


class PushSubscriptionRequest(BaseModel):
    """A browser PushSubscription, as returned by subscription.toJSON()."""

    endpoint: str = Field(..., min_length=10, max_length=2000)
    keys: dict[str, str]


@router.get("/push/public-key")
def push_public_key():
    """The VAPID public key the browser needs to subscribe."""
    if not settings.push_enabled:
        raise HTTPException(status_code=404, detail="Push notifications are disabled.")
    return {"public_key": get_push_service().keys.public_key}


@router.post("/push/subscribe", status_code=201)
def push_subscribe(
    request: PushSubscriptionRequest, user_id: str = Depends(current_user_id)
):
    """Register this browser to receive reminder notifications."""
    try:
        get_push_service().subscribe(user_id, request.model_dump())
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return {"success": True}


@router.delete("/push/subscribe")
def push_unsubscribe(endpoint: str = Query(..., max_length=2000)):
    """Stop sending notifications to this browser."""
    get_push_service().unsubscribe(endpoint)
    return {"success": True}


@router.get("/reminders/parse")
def parse_reminder_time(
    when: str = Query(..., min_length=1, max_length=120),
    timezone: str | None = Query(default=None, max_length=64),
):
    """Preview how a time like "friday at 6" will be understood, before saving a reminder."""
    due = parse_when(when, timezone)
    return {"due_at": due.isoformat() if due else None}


@router.get("/reminders/due")
def get_due_reminders(user_id: str = Depends(current_user_id)):
    """Reminders that are due now and haven't been notified yet (polled by the web app)."""
    return {"reminders": get_reminder_manager().get_due(user_id)}


@router.patch("/reminders/{reminder_id}/notified")
def mark_reminder_notified(reminder_id: int, user_id: str = Depends(current_user_id)):
    """Record that the user has been notified about a reminder."""
    if not get_reminder_manager().mark_notified(reminder_id, user_id):
        raise HTTPException(status_code=404, detail="Reminder not found.")
    return {"success": True}


@router.patch("/reminders/{reminder_id}/complete")
def complete_reminder(reminder_id: int, user_id: str = Depends(current_user_id)):
    """Mark a reminder as completed."""
    mgr = get_reminder_manager()
    updated = mgr.complete_reminder(reminder_id=reminder_id, user_id=user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Reminder not found.")
    return {"success": True, "message": "Reminder marked as completed."}


@router.delete("/reminders/{reminder_id}")
def delete_reminder(reminder_id: int, user_id: str = Depends(current_user_id)):
    """Delete a reminder by ID."""
    mgr = get_reminder_manager()
    deleted = mgr.delete_reminder(reminder_id=reminder_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Reminder not found.")
    return {"success": True, "message": "Reminder deleted."}
