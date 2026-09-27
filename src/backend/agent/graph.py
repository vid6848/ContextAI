"""LangGraph agent orchestration graph for ContextAI."""

from langgraph.graph import StateGraph, START, END
from src.backend.agent.state import AgentState
from src.backend.classifier.intent_classifier import IntentClassifier
from src.backend.llm.client import LLMClient

# Module-level singletons for performance and reuse
_default_classifier: IntentClassifier | None = None
_default_llm_client: LLMClient | None = None


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


def build_agent_graph(
    classifier: IntentClassifier | None = None,
    llm_client: LLMClient | None = None,
) -> StateGraph:
    """Construct and configure the LangGraph StateGraph workflow for ContextAI.

    Graph flow:
    START -> classify_intent -> generate_response -> END
    """
    workflow = StateGraph(AgentState)

    def classify_intent_node(state: AgentState) -> dict:
        """Classify user intent using TF-IDF + Logistic Regression."""
        message = state.get("message", "")
        if not message and state.get("messages"):
            last_msg = state["messages"][-1]
            message = last_msg.get("content", "") if isinstance(last_msg, dict) else str(last_msg)

        active_classifier = classifier or get_default_classifier()
        pred = active_classifier.predict(message)
        return {
            "intent": pred.intent,
            "current_intent": pred.intent,
            "confidence": pred.confidence,
        }

    def generate_response_node(state: AgentState) -> dict:
        """Generate response via Claude through LiteLLM."""
        message = state.get("message", "")
        if not message and state.get("messages"):
            last_msg = state["messages"][-1]
            message = last_msg.get("content", "") if isinstance(last_msg, dict) else str(last_msg)

        intent = state.get("intent") or state.get("current_intent") or "GENERAL"
        active_llm_client = llm_client or get_default_llm_client()
        response_text = active_llm_client.generate_response(message=message, intent=intent)
        return {
            "response": response_text,
            "final_response": response_text,
        }

    workflow.add_node("classify_intent", classify_intent_node)
    workflow.add_node("generate_response", generate_response_node)

    workflow.add_edge(START, "classify_intent")
    workflow.add_edge("classify_intent", "generate_response")
    workflow.add_edge("generate_response", END)

    return workflow


def get_agent_app(
    classifier: IntentClassifier | None = None,
    llm_client: LLMClient | None = None,
):
    """Return a compiled LangGraph runnable agent."""
    return build_agent_graph(classifier=classifier, llm_client=llm_client).compile()

