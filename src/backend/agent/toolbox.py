"""Function-calling tools exposed to the LLM, and their execution for one agent run."""

import json
from datetime import date
from typing import Any

from src.backend.rag.pipeline import DocumentRAGPipeline
from src.backend.tools.calculator import CalculatorTool
from src.backend.tools.crypto import CryptoTool
from src.backend.tools.weather import WeatherTool
from src.backend.tools.web_search import TavilySearchTool


def _fn(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


TOOL_SPECS: list[dict[str, Any]] = [
    _fn(
        "calculator",
        "Evaluate an arithmetic expression exactly. Use for any non-trivial math instead of mental arithmetic.",
        {"expression": {"type": "string", "description": "Python-style arithmetic, e.g. (250 * 15) / 2 or 2**10"}},
        ["expression"],
    ),
    _fn(
        "get_weather",
        "Current weather for a city (temperature in Celsius, conditions, humidity, wind).",
        {"city": {"type": "string", "description": "City name, optionally with country, e.g. 'Pune' or 'Paris, FR'"}},
        ["city"],
    ),
    _fn(
        "get_crypto_price",
        "Live USD price, 24h change and market cap of one cryptocurrency.",
        {"coin": {"type": "string", "description": "CoinGecko id or common symbol, e.g. bitcoin, eth, solana"}},
        ["coin"],
    ),
    _fn(
        "web_search",
        "Search the web for recent or factual information the model may not know. Returns numbered results.",
        {"query": {"type": "string", "description": "A focused search query"}},
        ["query"],
    ),
    _fn(
        "search_documents",
        "Search the PDFs the user uploaded. Returns numbered passages with document name and page.",
        {"query": {"type": "string", "description": "What to look for in the user's documents"}},
        ["query"],
    ),
]

# name -> (label while running, display name for the finished step)
TOOL_LABELS: dict[str, tuple[str, str]] = {
    "calculator": ("Calculating", "Calculator"),
    "get_weather": ("Checking the weather", "OpenWeather"),
    "get_crypto_price": ("Fetching crypto prices", "CoinGecko"),
    "web_search": ("Searching the web", "Tavily web search"),
    "search_documents": ("Searching your documents", "Document search"),
}
# Function name -> card type the UI renders for a successful result
CARD_KINDS = {"get_weather": "weather", "get_crypto_price": "crypto"}


class ToolBox:
    """Runs tool calls for one agent run and accumulates what the UI needs from them.

    Citation sources are numbered across every search in the run, so [n] in the final answer always
    points at the same source no matter which call produced it.
    """

    def __init__(
        self,
        *,
        calculator: CalculatorTool,
        weather: WeatherTool,
        crypto: CryptoTool,
        web: TavilySearchTool,
        rag: DocumentRAGPipeline,
        user_id: str,
    ) -> None:
        self.calculator = calculator
        self.weather = weather
        self.crypto = crypto
        self.web = web
        self.rag = rag
        self.user_id = user_id
        self.sources: list[dict[str, Any]] = []
        self.cards: list[dict[str, Any]] = []

    def run(self, name: str, args: dict[str, Any]) -> tuple[dict[str, Any], str]:
        """Execute a tool call. Returns (structured result for the trace, text for the model)."""
        if name == "calculator":
            result = self.calculator.evaluate(str(args.get("expression", "")))
        elif name == "get_weather":
            result = self.weather.get_weather(str(args.get("city", "")))
        elif name == "get_crypto_price":
            result = self.crypto.get_price(str(args.get("coin", "")))
        elif name == "web_search":
            result = self._web_search(str(args.get("query", "")))
        elif name == "search_documents":
            result = self._search_documents(str(args.get("query", "")))
        else:
            result = {"success": False, "error": f"Unknown tool '{name}'."}

        if result.get("success") and name in CARD_KINDS:
            self.cards.append({"tool": CARD_KINDS[name], "output": result})
        return result, self._for_model(result)

    def _web_search(self, query: str) -> dict[str, Any]:
        res = self.web.search(query)
        if not res.get("success"):
            return res
        numbered = []
        for r in res.get("results") or []:
            if not r.get("url"):
                continue
            n = len(self.sources) + 1
            excerpt = (r.get("content") or "")[:600]
            title = r.get("title") or r["url"]
            self.sources.append({"n": n, "kind": "web", "title": title, "url": r["url"], "excerpt": excerpt})
            numbered.append({"n": n, "title": title, "url": r["url"], "content": excerpt})
        today = date.today().isoformat()
        return {
            "success": True,
            "query": query,
            # Small models trust "upcoming" in stale articles; the date next to the results counters that
            "today": today,
            "note": f"Today is {today}. Anything these results describe as happening before today already happened.",
            "results": numbered,
        }

    def _search_documents(self, query: str) -> dict[str, Any]:
        chunks = self.rag.retrieve(query, limit=4, user_id=self.user_id)
        if not chunks:
            note = (
                "None of the user's documents mention this. Tell them it isn't in their documents; don't guess."
                if self.rag.count(self.user_id)
                else "The user hasn't uploaded any documents yet."
            )
            return {"success": True, "query": query, "passages": [], "note": note}
        passages = []
        for c in chunks:
            n = len(self.sources) + 1
            doc, page, text = c.get("document_name", "Document"), c.get("page_number", 1), c.get("content", "")
            source = {"n": n, "kind": "document", "document": doc, "page": page, "excerpt": text}
            if c.get("section"):
                source["section"] = c["section"]
            self.sources.append(source)
            passages.append({"n": n, "document": doc, "page": page, "text": text})
        return {"success": True, "query": query, "passages": passages}

    @staticmethod
    def _for_model(result: dict[str, Any]) -> str:
        """Tool result as compact JSON for the model (numbered sources keep their [n])."""
        return json.dumps(result, default=str)[:6000]
