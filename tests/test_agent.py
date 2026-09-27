"""Tests for LangGraph agent workflow."""

from unittest.mock import MagicMock
from src.backend.agent.state import AgentState
from src.backend.agent.graph import build_agent_graph, get_agent_app


def test_agent_state_keys():
    """Verify AgentState schema definition."""
    state: AgentState = {
        "user_id": "test_user",
        "current_intent": "greeting",
        "final_response": "Hello",
        "message": "Hello",
        "intent": "GENERAL",
        "confidence": 0.95,
        "response": "Hello",
    }
    assert state["user_id"] == "test_user"
    assert state["intent"] == "GENERAL"
    assert state["confidence"] == 0.95


def test_build_agent_graph():
    """Verify agent graph builder returns a StateGraph instance and can compile."""
    workflow = build_agent_graph()
    assert workflow is not None
    compiled_app = workflow.compile()
    assert compiled_app is not None


def test_agent_graph_execution_and_classifier_state():
    """Verify that user query flows through intent classification into graph state and triggers LLM."""
    mock_llm_client = MagicMock()
    mock_llm_client.generate_response.return_value = "It looks like rain today."

    app = get_agent_app(llm_client=mock_llm_client)
    initial_state = {"message": "What is the weather forecast for tomorrow?"}
    result = app.invoke(initial_state)

    # Verify classifier output reaches graph state
    assert result["intent"] == "WEATHER"
    assert result["current_intent"] == "WEATHER"
    assert isinstance(result["confidence"], float)
    assert result["confidence"] > 0.20

    # Verify LLM client was called with correct message and intent
    mock_llm_client.generate_response.assert_called_once_with(
        message="What is the weather forecast for tomorrow?",
        intent="WEATHER",
    )

    # Verify response is stored in graph state
    assert result["response"] == "It looks like rain today."
    assert result["final_response"] == "It looks like rain today."

