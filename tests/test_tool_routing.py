"""Tests for LangGraph Tool Routing and Document RAG integration."""

from unittest.mock import MagicMock, patch
import pymupdf
from src.backend.agent.graph import get_agent_app
from src.backend.rag.pipeline import DocumentRAGPipeline
from src.backend.tools.calculator import CalculatorTool
from src.backend.tools.weather import WeatherTool
from src.backend.tools.crypto import CryptoTool
from src.backend.tools.web_search import TavilySearchTool


def test_routing_weather_tool():
    """Verify WEATHER intent routes through weather tool and supplies result to Claude."""
    mock_llm = MagicMock()
    mock_llm.generate_response.return_value = "The temperature in Tokyo is 18°C."

    mock_weather = MagicMock(spec=WeatherTool)
    mock_weather.run.return_value = {
        "success": True,
        "location": "Tokyo, JP",
        "temperature": 18.0,
        "condition": "Clear",
    }

    app = get_agent_app(
        llm_client=mock_llm,
        weather_tool=mock_weather,
    )

    result = app.invoke({"message": "What is the weather in Tokyo?"})

    assert result["intent"] == "WEATHER"
    assert result["tool_name"] == "weather"
    assert result["tool_result"]["location"] == "Tokyo, JP"
    mock_weather.run.assert_called_once_with("What is the weather in Tokyo?")

    # Verify tool context reaches Claude
    mock_llm.generate_response.assert_called_once()
    context = mock_llm.generate_response.call_args.kwargs["context"]
    assert "Tool Execution Result (weather):" in context
    assert "Tokyo, JP" in context
    assert result["response"] == "The temperature in Tokyo is 18°C."


def test_routing_crypto_tool():
    """Verify CRYPTO intent routes to crypto tool and injects market data into Claude context."""
    mock_llm = MagicMock()
    mock_llm.generate_response.return_value = "Bitcoin is currently trading at $68,000."

    mock_crypto = MagicMock(spec=CryptoTool)
    mock_crypto.run.return_value = {
        "success": True,
        "coin": "bitcoin",
        "price_usd": 68000.0,
        "change_24h_percent": 2.5,
    }

    app = get_agent_app(
        llm_client=mock_llm,
        crypto_tool=mock_crypto,
    )

    result = app.invoke({"message": "What is the price of Bitcoin?"})

    assert result["intent"] == "CRYPTO"
    assert result["tool_name"] == "crypto"
    assert result["tool_result"]["price_usd"] == 68000.0
    mock_crypto.run.assert_called_once_with("What is the price of Bitcoin?")

    context = mock_llm.generate_response.call_args.kwargs["context"]
    assert "Tool Execution Result (crypto):" in context
    assert "68000" in context


def test_routing_calculator_tool():
    """Verify CALCULATOR intent routes to safe arithmetic tool."""
    mock_llm = MagicMock()
    mock_llm.generate_response.return_value = "25 multiplied by 4 is 100."

    app = get_agent_app(
        llm_client=mock_llm,
        calculator_tool=CalculatorTool(),
    )

    result = app.invoke({"message": "Calculate 25 * 4"})

    assert result["intent"] == "CALCULATOR"
    assert result["tool_name"] == "calculator"
    assert result["tool_result"]["success"]
    assert result["tool_result"]["result"] == 100

    context = mock_llm.generate_response.call_args.kwargs["context"]
    assert "Tool Execution Result (calculator):" in context
    assert "100" in context


def test_routing_web_search_tool():
    """Verify WEB_SEARCH intent routes to Tavily search tool."""
    mock_llm = MagicMock()
    mock_llm.generate_response.return_value = "Python 3.13 was released with free-threading support."

    mock_search = MagicMock(spec=TavilySearchTool)
    mock_search.run.return_value = {
        "success": True,
        "query": "Python 3.13 release notes",
        "results": [
            {"title": "Python 3.13 News", "url": "https://python.org", "content": "Free-threaded CPython released."}
        ],
    }

    app = get_agent_app(
        llm_client=mock_llm,
        tavily_tool=mock_search,
    )

    result = app.invoke({"message": "Search the web for Python 3.13 release notes"})

    assert result["intent"] == "WEB_SEARCH"
    assert result["tool_name"] == "web_search"
    assert len(result["tool_result"]["results"]) == 1

    context = mock_llm.generate_response.call_args.kwargs["context"]
    assert "Tool Execution Result (web_search):" in context
    assert "Free-threaded CPython" in context


def test_routing_document_rag_with_indexed_document(tmp_path):
    """Verify DOCUMENT intent retrieves relevant PDF chunks and passes to Claude with sources."""
    pdf_path = str(tmp_path / "handbook.pdf")
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "ContextAI Security Protocol. Multi-factor authentication is mandatory on all admin portals.")
    doc.save(pdf_path)
    doc.close()

    chroma_dir = str(tmp_path / "rag_chroma_route")
    rag = DocumentRAGPipeline(persist_dir=chroma_dir, collection_name="route_docs")
    rag.ingest_pdf(pdf_path)

    mock_llm = MagicMock()
    mock_llm.generate_response.return_value = (
        "According to handbook.pdf (Page 1), multi-factor authentication is mandatory on admin portals."
    )

    app = get_agent_app(
        llm_client=mock_llm,
        rag_pipeline=rag,
    )

    result = app.invoke({"message": "What does the document say about security authentication?"})

    assert result["intent"] == "DOCUMENT"
    assert result["tool_name"] == "document_rag"
    assert len(result["document_chunks"]) > 0
    assert len(result["rag_sources"]) > 0
    assert result["rag_sources"][0]["document"] == "handbook.pdf"

    context = mock_llm.generate_response.call_args.kwargs["context"]
    assert "Retrieved Document Content:" in context
    assert "[Source: handbook.pdf, Page: 1]" in context


def test_routing_document_rag_empty_no_documents(tmp_path):
    """Verify DOCUMENT intent returns clear message without inventing answer when no documents are indexed."""
    chroma_dir = str(tmp_path / "empty_rag_chroma")
    rag = DocumentRAGPipeline(persist_dir=chroma_dir, collection_name="empty_route_docs")

    mock_llm = MagicMock()

    app = get_agent_app(
        llm_client=mock_llm,
        rag_pipeline=rag,
    )

    result = app.invoke({"message": "Summarize the document"})

    assert result["intent"] == "DOCUMENT"
    assert "No documents have been indexed yet" in result["response"]
    # LLM should not be called to invent answers when no documents exist
    mock_llm.generate_response.assert_not_called()
