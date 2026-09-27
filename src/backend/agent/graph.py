"""LangGraph agent orchestration graph for ContextAI with Tool Routing and Document RAG."""

from typing import Any
from langgraph.graph import StateGraph, START, END
from src.backend.agent.state import AgentState
from src.backend.classifier.intent_classifier import IntentClassifier
from src.backend.llm.client import LLMClient
from src.backend.memory.sql_db import SQLiteManager
from src.backend.memory.vector_store import ChromaMemoryStore
from src.backend.tools.calculator import CalculatorTool
from src.backend.tools.weather import WeatherTool
from src.backend.tools.crypto import CryptoTool
from src.backend.tools.web_search import TavilySearchTool
from src.backend.rag.pipeline import DocumentRAGPipeline

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


def get_default_classifier() -> IntentClassifier:
    """Get or initialize singleton instance of IntentClassifier."""
    global _default_classifier
    if _default_classifier is None:
        _default_classifier = IntentClassifier()
        _default_classifier.train()
    return _default_classifier


def get_default_llm_client() -> LLMClient:
    """Get or initialize singleton instance of LLMClient."""
    global _default_llm_client
    if _default_llm_client is None:
        _default_llm_client = LLMClient()
    return _default_llm_client


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
        _default_rag_pipeline = DocumentRAGPipeline()
    return _default_rag_pipeline


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

        recent_history = active_sql.get_recent_messages(user_id=user_id, limit=6)

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

        context_data = {
            "conversation_history": recent_history,
            "semantic_memories": semantic_memories,
        }

        return {
            "user_id": user_id,
            "conversation_history": recent_history,
            "semantic_memories": semantic_memories,
            "context": context_data,
        }

    def classify_intent_node(state: AgentState) -> dict:
        """Classify user intent using TF-IDF + Logistic Regression."""
        message = _extract_message(state)
        active_classifier = classifier or get_default_classifier()
        pred = active_classifier.predict(message)
        return {
            "intent": pred.intent,
            "current_intent": pred.intent,
            "confidence": pred.confidence,
        }

    def route_by_intent(state: AgentState) -> str:
        """Route to appropriate tool node or directly to generate_response."""
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

    def calculator_node(state: AgentState) -> dict:
        """Execute calculator tool."""
        msg = _extract_message(state)
        tool = calculator_tool or get_default_calculator_tool()
        res = tool.run(msg)
        return {"tool_name": "calculator", "tool_result": res}

    def weather_node(state: AgentState) -> dict:
        """Execute weather tool."""
        msg = _extract_message(state)
        tool = weather_tool or get_default_weather_tool()
        res = tool.run(msg)
        return {"tool_name": "weather", "tool_result": res}

    def crypto_node(state: AgentState) -> dict:
        """Execute crypto tool."""
        msg = _extract_message(state)
        tool = crypto_tool or get_default_crypto_tool()
        res = tool.run(msg)
        return {"tool_name": "crypto", "tool_result": res}

    def web_search_node(state: AgentState) -> dict:
        """Execute web search tool."""
        msg = _extract_message(state)
        tool = tavily_tool or get_default_tavily_tool()
        res = tool.run(msg)
        return {"tool_name": "web_search", "tool_result": res}

    def document_rag_node(state: AgentState) -> dict:
        """Retrieve relevant PDF document chunks from ChromaDB."""
        msg = _extract_message(state)
        pipeline = rag_pipeline or get_default_rag_pipeline()
        chunks = pipeline.retrieve(msg, limit=4)
        if not chunks:
            return {
                "tool_name": "document_rag",
                "tool_result": {"success": False, "message": "No indexed documents found."},
                "document_chunks": [],
                "rag_sources": [],
            }
        _, sources = pipeline.format_context(chunks)
        return {
            "tool_name": "document_rag",
            "tool_result": {"success": True, "sources": sources},
            "document_chunks": chunks,
            "rag_sources": sources,
        }

    def generate_response_node(state: AgentState) -> dict:
        """Generate response via Claude through LiteLLM incorporating tools, RAG, and memory context."""
        message = _extract_message(state)
        intent = state.get("intent") or state.get("current_intent") or "GENERAL"

        # Handle DOCUMENT intent when no documents have been indexed
        if intent.upper() == "DOCUMENT":
            doc_chunks = state.get("document_chunks")
            if not doc_chunks:
                no_doc_msg = (
                    "No documents have been indexed yet. "
                    "Please ingest a PDF document first so I can answer questions from it."
                )
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
                f"Retrieved Document Content:\n{rag_text}\n"
                "Answer the user's question using the retrieved document content above. "
                "Include document name and page number citations in your answer."
            )

        # 2. Tool Execution Result
        tool_name = state.get("tool_name")
        tool_res = state.get("tool_result")
        if tool_name and tool_res:
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

        response_text = active_llm.generate_response(**call_kwargs)
        return {
            "response": response_text,
            "final_response": response_text,
        }

    def save_memory_node(state: AgentState) -> dict:
        """Save conversation history to SQLite and useful personal facts to ChromaDB."""
        user_id = state.get("user_id") or "default_user"
        message = _extract_message(state)
        response = state.get("response") or state.get("final_response") or ""

        active_sql = sql_manager or get_default_sql_manager()
        active_vs = vector_store or get_default_vector_store()

        if message:
            active_sql.save_message(user_id=user_id, role="user", message=message)
        if response:
            active_sql.save_message(user_id=user_id, role="assistant", message=response)

        if message and is_user_specific_memory(message):
            active_vs.add_memory(memory=message, user_id=user_id)

        return {}

    # Register nodes
    workflow.add_node("retrieve_memory", retrieve_memory_node)
    workflow.add_node("classify_intent", classify_intent_node)
    workflow.add_node("calculator", calculator_node)
    workflow.add_node("weather", weather_node)
    workflow.add_node("crypto", crypto_node)
    workflow.add_node("web_search", web_search_node)
    workflow.add_node("document_rag", document_rag_node)
    workflow.add_node("generate_response", generate_response_node)
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
