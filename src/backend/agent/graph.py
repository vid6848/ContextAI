"""LangGraph agent orchestration graph for ContextAI with Tool Routing and Document RAG."""

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from src.backend.agent.state import AgentState
from src.backend.agent.toolbox import TOOL_LABELS, TOOL_SPECS, ToolBox
from src.backend.classifier.intent_classifier import IntentClassifier
from src.backend.classifier.router import HybridRouter
from src.backend.core import tracing
from src.backend.core.config import settings
from src.backend.llm.client import LLMClient
from src.backend.memory.sql_db import SQLiteManager
from src.backend.memory.vector_store import ChromaMemoryStore
from src.backend.rag.pipeline import DocumentRAGPipeline
from src.backend.reminders.reminder_manager import ReminderManager
from src.backend.reminders.timeparse import resolve_timezone
from src.backend.tools.calculator import CalculatorTool
from src.backend.tools.crypto import CryptoTool
from src.backend.tools.weather import WeatherTool
from src.backend.tools.web_search import TavilySearchTool

# Module-level singletons for performance and reuse
_default_classifier: IntentClassifier | None = None
_default_llm_client: LLMClient | None = None
_default_sql_manager: SQLiteManager | None = None
_default_vector_store: ChromaMemoryStore | None = None
_default_calculator_tool: CalculatorTool | None = None
_default_weather_tool: WeatherTool | None = None
_default_crypto_tool: CryptoTool | None = None
_default_tavily_tool: TavilySearchTool | None = None
_default_rag_pipeline: DocumentRAGPipeline | None = None
_default_reminder_manager: ReminderManager | None = None


def get_default_classifier() -> IntentClassifier:
    """Get or initialize singleton instance of IntentClassifier."""
    global _default_classifier
    if _default_classifier is None:
        _default_classifier = IntentClassifier()
        _default_classifier.train()
    return _default_classifier


_default_router: HybridRouter | None = None


def get_default_router() -> HybridRouter:
    """Hybrid router built on the default classifier plus sentence embeddings."""
    global _default_router
    if _default_router is None:
        _default_router = HybridRouter(get_default_classifier())
    return _default_router


def get_default_llm_client() -> LLMClient:
    """Get or initialize singleton instance of LLMClient."""
    global _default_llm_client
    if _default_llm_client is None:
        _default_llm_client = LLMClient()
    return _default_llm_client


_default_utility_llm: LLMClient | None = None


def get_default_utility_llm() -> LLMClient:
    """LLM for side tasks (titles, memory), on a different model so it has its own rate-limit quota."""
    global _default_utility_llm
    if _default_utility_llm is None:
        _default_utility_llm = LLMClient(
            model_name=settings.utility_model_name or settings.fallback_model_name,
            fallback_model_name=settings.model_name,
        )
    return _default_utility_llm


def get_default_sql_manager() -> SQLiteManager:
    """Get or initialize singleton instance of SQLiteManager."""
    global _default_sql_manager
    if _default_sql_manager is None:
        _default_sql_manager = SQLiteManager()
    return _default_sql_manager


def get_default_vector_store() -> ChromaMemoryStore:
    """Get or initialize singleton instance of ChromaMemoryStore."""
    global _default_vector_store
    if _default_vector_store is None:
        if settings.database_url:
            from src.backend.db.pg_stores import PgMemoryStore

            _default_vector_store = PgMemoryStore(settings.database_url)
        else:
            _default_vector_store = ChromaMemoryStore()
    return _default_vector_store


def get_default_calculator_tool() -> CalculatorTool:
    """Get or initialize singleton instance of CalculatorTool."""
    global _default_calculator_tool
    if _default_calculator_tool is None:
        _default_calculator_tool = CalculatorTool()
    return _default_calculator_tool


def get_default_weather_tool() -> WeatherTool:
    """Get or initialize singleton instance of WeatherTool."""
    global _default_weather_tool
    if _default_weather_tool is None:
        _default_weather_tool = WeatherTool()
    return _default_weather_tool


def get_default_crypto_tool() -> CryptoTool:
    """Get or initialize singleton instance of CryptoTool."""
    global _default_crypto_tool
    if _default_crypto_tool is None:
        _default_crypto_tool = CryptoTool()
    return _default_crypto_tool


def get_default_tavily_tool() -> TavilySearchTool:
    """Get or initialize singleton instance of TavilySearchTool."""
    global _default_tavily_tool
    if _default_tavily_tool is None:
        _default_tavily_tool = TavilySearchTool()
    return _default_tavily_tool


def get_default_rag_pipeline() -> DocumentRAGPipeline:
    """Get or initialize singleton instance of DocumentRAGPipeline."""
    global _default_rag_pipeline
    if _default_rag_pipeline is None:
        if settings.database_url:
            from src.backend.db.pg_stores import PgDocumentRAGPipeline

            _default_rag_pipeline = PgDocumentRAGPipeline(settings.database_url)
        else:
            _default_rag_pipeline = DocumentRAGPipeline()
    return _default_rag_pipeline


def get_default_reminder_manager() -> ReminderManager:
    """Get or initialize singleton instance of ReminderManager."""
    global _default_reminder_manager
    if _default_reminder_manager is None:
        _default_reminder_manager = ReminderManager()
    return _default_reminder_manager


def is_user_specific_memory(message: str) -> bool:
    """Determine whether a message contains useful user-specific information for long-term memory.

    Uses deterministic heuristic matching for personal facts, preferences, and explicit notes.
    Trivial messages (greetings, chitchat, generic queries) are excluded.
    """
    clean_msg = message.strip().lower()

    if len(clean_msg.split()) < 3:
        return False

    trivial_phrases = {
        "hello", "hi", "hey", "good morning", "good evening", "good night",
        "how are you", "what's up", "thank you", "thanks", "bye", "goodbye",
    }
    if clean_msg in trivial_phrases:
        return False

    memory_indicators = [
        "my name is", "i am ", "i'm ", "call me ",
        "i like ", "i love ", "i prefer ", "i dislike ", "i hate ", "i enjoy ",
        "i live in ", "i am from ", "i work as ", "i work at ", "my job is ",
        "my favorite ", "my hobby ", "my goal is ", "my birthday ",
        "remember that", "remember:", "note that", "keep in mind", "please remember",
        "i have an allergy", "i am allergic", "i speak ",
        "my email ", "my address ", "my pet ", "my dog ", "my cat ",
    ]

    return any(indicator in clean_msg for indicator in memory_indicators)


TOOL_DISPLAY = {
    "calculator": ("Calculating", "Calculator"),
    "weather": ("Checking the weather", "OpenWeather"),
    "crypto": ("Fetching crypto prices", "CoinGecko"),
    "web_search": ("Searching the web", "Tavily web search"),
}
MAX_STEP_DETAIL_CHARS = 4000
# Tools whose structured result the UI renders as a card under the answer
CARD_TOOLS = {"weather", "crypto"}
CITATION_RULES = (
    "Cite each claim with the source number in square brackets right after it, like [1] or [2][3]. "
    "Don't write document names, page numbers or URLs in the text; the app shows them next to the citations. "
    "If the sources don't contain the answer, say so instead of guessing."
)


def web_sources(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn web search results into numbered citation sources."""
    return [
        {"n": n, "kind": "web", "title": r.get("title") or r.get("url", ""), "url": r.get("url", ""),
         "excerpt": (r.get("content") or "")[:600]}
        for n, r in enumerate(result.get("results") or [], start=1)
        if r.get("url")
    ]


def _compact(value: Any) -> Any:
    """Keep step details small enough to stream and store alongside the message."""
    text = json.dumps(value, default=str)
    if len(text) <= MAX_STEP_DETAIL_CHARS:
        return value
    return text[:MAX_STEP_DETAIL_CHARS] + "…"


@contextmanager
def agent_step(step_id: str, label: str) -> Iterator[dict[str, Any]]:
    """Time a unit of agent work and stream its start/end as `step` events.

    The body may update step["label"] and step["detail"], and set step["failed"] = True to report a handled
    failure (e.g. a tool returning an error) without raising. Under graph.invoke() the stream writer is a
    no-op, so the same nodes serve both the streaming and non-streaming endpoints.
    """
    writer = get_stream_writer()
    step: dict[str, Any] = {"id": step_id, "label": label, "status": "running"}
    writer({"type": "step", **step})
    started = time.perf_counter()
    kind = "retriever" if step_id == "tool:document_rag" else "tool" if step_id.startswith("tool:") else "span"
    with tracing.span(step_id, kind) as observation:
        try:
            yield step
            step["status"] = "error" if step.pop("failed", False) else "done"
        except Exception:
            step["status"] = "error"
            raise
        finally:
            step["duration_ms"] = round((time.perf_counter() - started) * 1000)
            writer({"type": "step", **step})
            detail = step.get("detail") or {}
            observation.update(
                input=detail.get("input"), output=detail.get("output", detail) or None,
                metadata={"label": step["label"]}, level="ERROR" if step["status"] == "error" else None,
            )


def answer_cards(state: AgentState) -> list[dict[str, Any]]:
    """Cards for the UI: every successful weather/crypto result, from either routing path."""
    if state.get("cards"):
        return state["cards"]
    card = tool_card(state)
    return [{"tool": state["tool_name"], "output": card}] if card else []


def tool_card(state: AgentState) -> dict[str, Any] | None:
    """Structured tool result for the UI card, when the tool has one and succeeded."""
    result = state.get("tool_result") or {}
    if state.get("tool_name") in CARD_TOOLS and result.get("success"):
        return result
    return None


def choose_route(confidence: float) -> str:
    """Route for the non-hybrid modes ("hybrid" uses HybridRouter.decide instead)."""
    if settings.router_mode == "classifier":
        return "classifier"
    if settings.router_mode == "llm":
        return "llm"
    return "classifier" if confidence >= settings.hybrid_confidence_threshold else "llm"


AGENT_SYSTEM_PROMPT = (
    "You are ContextAI, a helpful personal assistant. It is now {now} in the user's timezone ({tz}).\n"
    "You can call tools: a calculator, current weather, live crypto prices, web search, reminders, and a "
    "search over the PDFs the user uploaded. Call a tool whenever the answer depends on live data, exact arithmetic, "
    "recent facts or the user's documents. When a question has several parts, call several tools at once. "
    "Never invent tool results; if a tool fails, say so briefly and answer what you can.\n"
    "Search results can be out of date: compare any dates you find with today's date, treat earlier dates as "
    "past events, and say so when the question is about the future.\n"
    "Web and document results are numbered. " + "{citations}"
)


def build_chat_messages(state: AgentState) -> list[dict[str, Any]]:
    """System prompt (with long-term memories), prior turns as real chat messages, then the new message."""
    tz = resolve_timezone(state.get("timezone"))
    now = datetime.now(tz).strftime("%A %d %B %Y, %H:%M")
    system = AGENT_SYSTEM_PROMPT.format(now=now, tz=tz.key, citations=CITATION_RULES)
    memories = state.get("semantic_memories") or []
    if memories:
        system += "\n\nThings the user told you before (use them when relevant):\n" + "\n".join(
            f"- {m}" for m in memories
        )
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for m in state.get("conversation_history") or []:
        role = "assistant" if m.get("role") == "assistant" else "user"
        messages.append({"role": role, "content": m.get("message", "")})
    messages.append({"role": "user", "content": _extract_message(state)})
    return messages


def _tool_names(calls: list[dict[str, Any]]) -> str:
    names = list(dict.fromkeys(TOOL_LABELS.get(c["function"]["name"], ("", c["function"]["name"]))[1] for c in calls))
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _extract_message(state: AgentState) -> str:
    """Helper to extract user message string from state."""
    message = state.get("message", "")
    if not message and state.get("messages"):
        last_msg = state["messages"][-1]
        message = last_msg.get("content", "") if isinstance(last_msg, dict) else str(last_msg)
    return message


def build_agent_graph(
    classifier: IntentClassifier | None = None,
    llm_client: LLMClient | None = None,
    sql_manager: SQLiteManager | None = None,
    vector_store: ChromaMemoryStore | None = None,
    calculator_tool: CalculatorTool | None = None,
    weather_tool: WeatherTool | None = None,
    crypto_tool: CryptoTool | None = None,
    tavily_tool: TavilySearchTool | None = None,
    rag_pipeline: DocumentRAGPipeline | None = None,
) -> StateGraph:
    """Construct and configure the LangGraph StateGraph workflow for ContextAI.

    Graph flow:
    START
      ↓
    retrieve_memory
      ↓
    classify_intent
      ↓
    route_by_intent
      ├── calculator
      ├── weather
      ├── crypto
      ├── web_search
      ├── document_rag
      └── generate_response
             ↓
        save_memory
             ↓
            END
    """
    workflow = StateGraph(AgentState)

    def retrieve_memory_node(state: AgentState) -> dict:
        """Retrieve recent conversation history from SQLite and semantic memories from ChromaDB."""
        user_id = state.get("user_id") or "default_user"
        message = _extract_message(state)

        active_sql = sql_manager or get_default_sql_manager()
        active_vs = vector_store or get_default_vector_store()

        with agent_step("memory", "Recalling memory") as step:
            recent_history = active_sql.get_recent_messages(
                user_id=user_id,
                limit=6,
                conversation_id=state.get("conversation_id"),
            )

            semantic_memories: list[str] = []
            if message:
                try:
                    semantic_memories = active_vs.get_relevant_memories(
                        query=message,
                        user_id=user_id,
                        limit=3,
                    )
                except Exception:
                    semantic_memories = []

            step["label"] = (
                f"Recalled {len(semantic_memories)} long-term "
                f"{'memory' if len(semantic_memories) == 1 else 'memories'}"
                if semantic_memories
                else "No relevant long-term memories"
            )
            step["detail"] = {"memories": semantic_memories, "recent_messages": len(recent_history)}

        context_data = {
            "conversation_history": recent_history,
            "semantic_memories": semantic_memories,
        }

        return {
            "user_id": user_id,
            "conversation_history": recent_history,
            "semantic_memories": semantic_memories,
            "context": context_data,
            "steps": [step],
        }

    def classify_intent_node(state: AgentState) -> dict:
        """Classify intent and decide the route: fixed single-tool fast path, or the LLM tool agent."""
        message = _extract_message(state)
        active_classifier = classifier or get_default_classifier()
        attachments = state.get("attachments") or []
        with agent_step("intent", "Classifying intent") as step:
            if attachments:
                # The user pointed at specific files; no need to guess
                intent, confidence, route = "DOCUMENT", 1.0, "classifier"
                step["label"] = f"Routed to your attached {'file' if len(attachments) == 1 else 'files'}"
                step["detail"] = {"intent": intent, "attachments": attachments}
            elif settings.router_mode == "hybrid":
                decision = get_default_router().decide(message, settings.hybrid_confidence_threshold)
                intent, confidence, route = decision.intent, decision.confidence, decision.route
                step["detail"] = {"intent": intent, "similarity": round(confidence, 3), "route": route,
                                  "reason": decision.reason}
                step["label"] = (
                    f"Classified intent: {intent} ({confidence:.0%} match)"
                    if route == "classifier"
                    else f"Letting the model choose tools ({decision.reason})"
                )
            else:
                pred = active_classifier.predict(message)
                intent, confidence = pred.intent, pred.confidence
                route = choose_route(confidence)
                step["detail"] = {"intent": intent, "confidence": round(confidence, 3), "route": route}
                step["label"] = (
                    f"Classified intent: {intent} ({confidence:.0%})"
                    if route == "classifier"
                    else f"Letting the model choose tools (classifier guessed {intent}, {confidence:.0%})"
                )
        return {
            "intent": intent,
            "current_intent": intent,
            "confidence": confidence,
            "route": route,
            "steps": [step],
        }

    def route_by_intent(state: AgentState) -> str:
        """Route to the LLM tool agent, a fixed tool node, or directly to generate_response."""
        if state.get("route") == "llm":
            return "llm_agent"
        intent = (state.get("intent") or state.get("current_intent") or "GENERAL").upper()
        if intent == "CALCULATOR":
            return "calculator"
        elif intent == "WEATHER":
            return "weather"
        elif intent == "CRYPTO":
            return "crypto"
        elif intent == "WEB_SEARCH":
            return "web_search"
        elif intent == "DOCUMENT":
            return "document_rag"
        else:
            return "generate_response"

    def run_tool(name: str, tool: Any, msg: str) -> dict:
        """Run a tool inside a timed step that records its input and output."""
        running_label, display = TOOL_DISPLAY[name]
        with agent_step(f"tool:{name}", running_label) as step:
            res = tool.run(msg)
            ok = bool(res.get("success", True))
            step["label"] = f"Used {display}" if ok else f"{display} failed: {res.get('error', 'unknown error')}"
            step["failed"] = not ok
            step["detail"] = {"input": msg, "output": _compact(res)}
        return {"tool_name": name, "tool_result": res, "steps": [step]}

    def calculator_node(state: AgentState) -> dict:
        """Execute calculator tool."""
        return run_tool("calculator", calculator_tool or get_default_calculator_tool(), _extract_message(state))

    def weather_node(state: AgentState) -> dict:
        """Execute weather tool."""
        return run_tool("weather", weather_tool or get_default_weather_tool(), _extract_message(state))

    def crypto_node(state: AgentState) -> dict:
        """Execute crypto tool."""
        return run_tool("crypto", crypto_tool or get_default_crypto_tool(), _extract_message(state))

    def web_search_node(state: AgentState) -> dict:
        """Execute web search tool; its results become numbered citation sources."""
        update = run_tool("web_search", tavily_tool or get_default_tavily_tool(), _extract_message(state))
        if update["tool_result"].get("success"):
            update["rag_sources"] = web_sources(update["tool_result"])
        return update

    def document_rag_node(state: AgentState) -> dict:
        """Retrieve relevant PDF document chunks from ChromaDB."""
        msg = _extract_message(state)
        pipeline = rag_pipeline or get_default_rag_pipeline()
        with agent_step("tool:document_rag", "Searching your documents") as step:
            attachments = state.get("attachments") or None
            chunks = pipeline.retrieve(
                msg, limit=6 if attachments else 4, user_id=state.get("user_id") or "default_user",
                document_names=attachments,
            )
            _, sources = pipeline.format_context(chunks)
            step["label"] = (
                f"Found {len(chunks)} relevant {'passage' if len(chunks) == 1 else 'passages'}"
                if chunks
                else "No relevant passages in your documents"
            )
            step["detail"] = {"input": msg, "sources": sources}
        if not chunks:
            return {
                "tool_name": "document_rag",
                "tool_result": {"success": False, "message": "No indexed documents found."},
                "document_chunks": [],
                "rag_sources": [],
                "steps": [step],
            }
        return {
            "tool_name": "document_rag",
            "tool_result": {"success": True, "sources": sources},
            "document_chunks": chunks,
            "rag_sources": sources,
            "steps": [step],
        }

    def llm_agent_node(state: AgentState, config: RunnableConfig) -> dict:
        """Function-calling loop: the model picks tools (possibly several, over several rounds), then answers.

        Each model round is a "plan" step and each tool call its own step, so the trace shows the chain.
        """
        configurable = config.get("configurable", {}) if config else {}
        cancel_event = configurable.get("cancel_event")
        writer = get_stream_writer()
        active_llm = llm_client or get_default_llm_client()
        toolbox = ToolBox(
            calculator=calculator_tool or get_default_calculator_tool(),
            weather=weather_tool or get_default_weather_tool(),
            crypto=crypto_tool or get_default_crypto_tool(),
            web=tavily_tool or get_default_tavily_tool(),
            rag=rag_pipeline or get_default_rag_pipeline(),
            reminders=get_default_reminder_manager(),
            user_id=state.get("user_id") or "default_user",
            timezone=state.get("timezone"),
        )
        messages = build_chat_messages(state)
        steps: list[dict[str, Any]] = []
        tools_used: list[str] = []
        answer: list[str] = []

        for round_no in range(settings.max_tool_rounds + 1):
            # The last round withholds tools so the model has to answer
            tools = TOOL_SPECS if round_no < settings.max_tool_rounds else None
            plan = {"id": f"plan:{round_no}", "status": "running",
                    "label": "Deciding how to answer" if round_no == 0 else "Reading the results"}
            writer({"type": "step", **plan})
            started = time.perf_counter()
            message: dict[str, Any] = {}
            for kind, payload in active_llm.chat_round(messages, tools=tools, cancel_event=cancel_event):
                if kind == "token":
                    if plan["status"] == "running":
                        plan.update(status="done", label="Answering directly" if round_no == 0 else plan["label"],
                                    duration_ms=round((time.perf_counter() - started) * 1000))
                        writer({"type": "step", **plan})
                    answer.append(payload)
                    writer({"type": "token", "text": payload})
                else:
                    message = payload
            calls = message.get("tool_calls") or []
            if plan["status"] == "running":
                plan.update(status="done", duration_ms=round((time.perf_counter() - started) * 1000),
                            label=f"Decided to use {_tool_names(calls)}" if calls else plan["label"])
                if calls:
                    plan["detail"] = {
                        "calls": [
                            {"tool": c["function"]["name"], "arguments": c["function"].get("arguments")}
                            for c in calls
                        ]
                    }
                writer({"type": "step", **plan})
            steps.append(plan)

            if not calls or (cancel_event and cancel_event.is_set()):
                break
            messages.append(message)
            for i, call in enumerate(calls):
                name = call["function"]["name"]
                running, display = TOOL_LABELS.get(name, ("Running a tool", name))
                try:
                    args = json.loads(call["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                with agent_step(f"tool:{name}:{round_no}.{i}", running) as step:
                    result, for_model = toolbox.run(name, args)
                    ok = bool(result.get("success"))
                    error = result.get("error", "unknown error")
                    step["label"] = f"Used {display}" if ok else f"{display} failed: {error}"
                    step["failed"] = not ok
                    step["detail"] = {"input": args, "output": _compact(result)}
                steps.append(step)
                tools_used.append(name)
                messages.append({"role": "tool", "tool_call_id": call.get("id"), "name": name, "content": for_model})

        response_text = "".join(answer)
        return {
            "response": response_text,
            "final_response": response_text,
            "stopped": bool(cancel_event and cancel_event.is_set()),
            "steps": steps,
            "tools_used": tools_used,
            "tool_name": tools_used[0] if tools_used else None,
            "rag_sources": toolbox.sources,
            "cards": toolbox.cards,
        }

    def generate_response_node(state: AgentState, config: RunnableConfig) -> dict:
        """Generate response with the configured LLM incorporating tools, RAG, and memory context."""
        message = _extract_message(state)
        intent = state.get("intent") or state.get("current_intent") or "GENERAL"

        # Handle DOCUMENT intent when no documents have been indexed
        if intent.upper() == "DOCUMENT":
            doc_chunks = state.get("document_chunks")
            if not doc_chunks:
                pipeline = rag_pipeline or get_default_rag_pipeline()
                has_docs = pipeline.count(state.get("user_id") or "default_user") > 0
                no_doc_msg = (
                    "I couldn't find anything about that in your documents. "
                    "Try rephrasing, or ask about something they cover."
                    if has_docs
                    else "No documents have been indexed yet. "
                    "Please ingest a PDF document first so I can answer questions from it."
                )
                get_stream_writer()({"type": "token", "text": no_doc_msg})
                return {
                    "response": no_doc_msg,
                    "final_response": no_doc_msg,
                }

        context_sections: list[str] = []

        # 1. Document RAG context
        if state.get("document_chunks"):
            pipeline = rag_pipeline or get_default_rag_pipeline()
            rag_text, _ = pipeline.format_context(state["document_chunks"])
            context_sections.append(
                f"Numbered passages from the user's documents:\n{rag_text}\n"
                f"Answer the user's question from these passages. {CITATION_RULES}"
            )

        # 2. Tool Execution Result
        tool_name = state.get("tool_name")
        tool_res = state.get("tool_result")
        if tool_name == "web_search" and state.get("rag_sources"):
            results_text = "\n\n".join(
                f"[{s['n']}] {s['title']} ({s['url']})\n{s['excerpt']}" for s in state["rag_sources"]
            )
            context_sections.append(
                f"Numbered web search results:\n{results_text}\n"
                f"Answer the user's question from these results. {CITATION_RULES}"
            )
        elif tool_name and tool_res and tool_name != "document_rag":
            context_sections.append(
                f"Tool Execution Result ({tool_name}):\n{tool_res}\n"
                "Use the tool result above to provide an accurate, helpful, and natural-language answer to the user."
            )

        # 3. Semantic long-term memories
        memories = state.get("semantic_memories") or []
        if memories:
            mems_formatted = "\n".join(f"- {m}" for m in memories)
            context_sections.append(f"Relevant Long-Term Memories:\n{mems_formatted}")

        # 4. Short-term conversation history
        history = state.get("conversation_history") or []
        if history:
            hist_formatted = "\n".join(
                f"{m.get('role', 'user').capitalize()}: {m.get('message', '')}"
                for m in history
            )
            context_sections.append(f"Recent Conversation History:\n{hist_formatted}")

        combined_context = "\n\n".join(context_sections) if context_sections else None

        active_llm = llm_client or get_default_llm_client()
        call_kwargs: dict[str, Any] = {
            "message": message,
            "intent": intent,
        }
        if combined_context:
            call_kwargs["context"] = combined_context

        configurable = config.get("configurable", {}) if config else {}
        if not configurable.get("stream"):
            response_text = active_llm.generate_response(**call_kwargs)
            return {
                "response": response_text,
                "final_response": response_text,
            }

        # Streaming: forward each delta to the client as it arrives; stop early if cancelled
        cancel_event = configurable.get("cancel_event")
        writer = get_stream_writer()
        parts: list[str] = []
        for delta in active_llm.stream_response(cancel_event=cancel_event, **call_kwargs):
            parts.append(delta)
            writer({"type": "token", "text": delta})
        response_text = "".join(parts)
        return {
            "response": response_text,
            "final_response": response_text,
            "stopped": bool(cancel_event and cancel_event.is_set()),
        }

    def save_memory_node(state: AgentState) -> dict:
        """Save conversation history to SQLite and useful personal facts to ChromaDB."""
        user_id = state.get("user_id") or "default_user"
        message = _extract_message(state)
        response = state.get("response") or state.get("final_response") or ""

        active_sql = sql_manager or get_default_sql_manager()
        active_vs = vector_store or get_default_vector_store()

        conversation_id = state.get("conversation_id")
        saved: dict[str, int] = {}
        if message:
            attachments = state.get("attachments")
            saved["user_message_id"] = active_sql.save_message(
                user_id=user_id,
                role="user",
                message=message,
                conversation_id=conversation_id,
                metadata={"attachments": attachments} if attachments else None,
            )
        if response:
            saved["assistant_message_id"] = active_sql.save_message(
                user_id=user_id,
                role="assistant",
                message=response,
                conversation_id=conversation_id,
                metadata={
                    "intent": state.get("intent"),
                    "confidence": state.get("confidence"),
                    "tool_used": state.get("tool_name"),
                    "sources": state.get("rag_sources"),
                    "tool_output": tool_card(state),
                    "cards": answer_cards(state),
                    "tools_used": state.get("tools_used") or ([state["tool_name"]] if state.get("tool_name") else []),
                    "steps": state.get("steps") or [],
                    "stopped": bool(state.get("stopped")),
                    # Links 👍/👎 on this answer to its Langfuse trace (None when tracing is off)
                    "trace_id": tracing.current_trace_id(),
                },
            )

        # In "llm" mode the API layer extracts facts after the reply is sent (see update_long_term_memory)
        if settings.memory_mode == "heuristic" and message and is_user_specific_memory(message):
            active_vs.add_memory(memory=message, user_id=user_id)

        return saved

    # Register nodes
    workflow.add_node("retrieve_memory", retrieve_memory_node)
    workflow.add_node("classify_intent", classify_intent_node)
    workflow.add_node("calculator", calculator_node)
    workflow.add_node("weather", weather_node)
    workflow.add_node("crypto", crypto_node)
    workflow.add_node("web_search", web_search_node)
    workflow.add_node("document_rag", document_rag_node)
    workflow.add_node("generate_response", generate_response_node)
    workflow.add_node("llm_agent", llm_agent_node)
    workflow.add_node("save_memory", save_memory_node)

    # Register edges
    workflow.add_edge(START, "retrieve_memory")
    workflow.add_edge("retrieve_memory", "classify_intent")

    # Conditional routing after classification
    workflow.add_conditional_edges(
        "classify_intent",
        route_by_intent,
        {
            "calculator": "calculator",
            "weather": "weather",
            "crypto": "crypto",
            "web_search": "web_search",
            "document_rag": "document_rag",
            "generate_response": "generate_response",
            "llm_agent": "llm_agent",
        },
    )

    # Tool and RAG nodes proceed to generate_response
    workflow.add_edge("calculator", "generate_response")
    workflow.add_edge("weather", "generate_response")
    workflow.add_edge("crypto", "generate_response")
    workflow.add_edge("web_search", "generate_response")
    workflow.add_edge("document_rag", "generate_response")

    # Final response generation proceeds to save_memory and END
    workflow.add_edge("generate_response", "save_memory")
    workflow.add_edge("llm_agent", "save_memory")
    workflow.add_edge("save_memory", END)

    return workflow


def get_agent_app(
    classifier: IntentClassifier | None = None,
    llm_client: LLMClient | None = None,
    sql_manager: SQLiteManager | None = None,
    vector_store: ChromaMemoryStore | None = None,
    calculator_tool: CalculatorTool | None = None,
    weather_tool: WeatherTool | None = None,
    crypto_tool: CryptoTool | None = None,
    tavily_tool: TavilySearchTool | None = None,
    rag_pipeline: DocumentRAGPipeline | None = None,
):
    """Return a compiled LangGraph runnable agent."""
    return build_agent_graph(
        classifier=classifier,
        llm_client=llm_client,
        sql_manager=sql_manager,
        vector_store=vector_store,
        calculator_tool=calculator_tool,
        weather_tool=weather_tool,
        crypto_tool=crypto_tool,
        tavily_tool=tavily_tool,
        rag_pipeline=rag_pipeline,
    ).compile()
