"""Function-calling tools exposed to the LLM, and their execution for one agent run."""

import json
import re
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from src.backend.rag.pipeline import DocumentRAGPipeline
from src.backend.reminders.reminder_manager import ReminderManager
from src.backend.reminders.timeparse import resolve_timezone
from src.backend.tools.calculator import CalculatorTool
from src.backend.tools.crypto import CryptoTool
from src.backend.tools.weather import WeatherTool, extract_city_from_query
from src.backend.tools.web_search import TavilySearchTool

# Fits a whole-document read (OVERVIEW_PASSAGES passages of ~900 characters) without cutting the JSON
MAX_RESULT_CHARS = 32000


def _fn(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


CITY_PARAM = {
    "type": "string",
    "description": "City named by the user, optionally with a country code. For a landmark or country, its city.",
}
UNITS_PARAM = {"type": "string", "enum": ["metric", "imperial"], "description": "imperial for Fahrenheit and mph"}

TOOL_SPECS: list[dict[str, Any]] = [
    _fn(
        "calculator",
        "Evaluate an arithmetic expression exactly. Use for any non-trivial math instead of mental arithmetic.",
        {"expression": {"type": "string", "description": "Python-style arithmetic, e.g. (250 * 15) / 2 or 2**10"}},
        ["expression"],
    ),
    _fn(
        "get_weather",
        "Weather right now in a city: temperature, feels like, conditions, humidity, wind, clouds, visibility, "
        "sunrise, sunset and the city's local time.",
        {"city": CITY_PARAM, "units": UNITS_PARAM},
        ["city"],
    ),
    _fn(
        "get_forecast",
        "Forecast for a city, up to 5 days ahead: daily high, low, conditions and chance of rain. Use for anything "
        "after this moment (tonight, tomorrow, a weekday, 'will it rain'). Pass `date` for one day, which also "
        "returns its 3-hour steps.",
        {
            "city": CITY_PARAM,
            "date": {"type": "string", "description": "Day in YYYY-MM-DD; omit for all 5 days"},
            "units": UNITS_PARAM,
        },
        ["city"],
    ),
    _fn(
        "get_air_quality",
        "Current air quality in a city: AQI from 1 (good) to 5 (very poor) and pollutant levels (PM2.5, PM10...).",
        {"city": CITY_PARAM},
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
        "create_reminder",
        "Set a reminder for the user. Resolve relative times yourself using the current date and time.",
        {
            "text": {"type": "string", "description": "What to remind them about, e.g. 'Call mom'"},
            "when": {"type": "string", "description": "ISO 8601 local date-time, e.g. 2026-10-24T17:00"},
        },
        ["text", "when"],
    ),
    _fn("list_reminders", "List the user's upcoming (pending) reminders.", {}, []),
    _fn(
        "search_documents",
        "Read the PDFs the user uploaded. Returns numbered passages with document name and page. Handles a topic "
        "('refund policy'), whole-document requests ('summarize', 'key points') and pages ('page 3', 'last page').",
        {
            "query": {"type": "string", "description": "What to look for, in the user's own words"},
            "document": {"type": "string", "description": "Only this document, by file name; omit for all in scope"},
        },
        ["query"],
    ),
    _fn("list_documents", "List the PDFs the user uploaded, with their page counts.", {}, []),
]

# name -> (label while running, display name for the finished step)
TOOL_LABELS: dict[str, tuple[str, str]] = {
    "calculator": ("Calculating", "Calculator"),
    "get_weather": ("Checking the weather", "OpenWeather"),
    "get_forecast": ("Checking the forecast", "OpenWeather"),
    "get_air_quality": ("Checking the air quality", "OpenWeather"),
    "get_crypto_price": ("Fetching crypto prices", "CoinGecko"),
    "web_search": ("Searching the web", "Tavily web search"),
    "search_documents": ("Searching your documents", "Document search"),
    "list_documents": ("Checking your documents", "Your documents"),
    "create_reminder": ("Setting a reminder", "Reminders"),
    "list_reminders": ("Checking your reminders", "Reminders"),
}
WEATHER_TOOLS = {"get_weather", "get_forecast", "get_air_quality"}
# Function name -> card type the UI renders for a successful result
CARD_KINDS = {
    "get_weather": "weather", "get_forecast": "weather", "get_crypto_price": "crypto", "create_reminder": "reminder",
}


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
        reminders: ReminderManager,
        user_id: str,
        timezone: str | None = None,
        documents: list[str] | None = None,
        conversation_text: str = "",
        message: str = "",
    ) -> None:
        self.calculator = calculator
        self.weather = weather
        self.crypto = crypto
        self.web = web
        self.rag = rag
        self.reminders = reminders
        self.user_id = user_id
        self.timezone = timezone
        self.documents = documents or None  # files this chat is about; searches stay on them
        # The message, recent chat and memories: where a place the model uses must have come from
        self.conversation_text = conversation_text.lower()
        self.message = message
        self.sources: list[dict[str, Any]] = []
        self.cards: list[dict[str, Any]] = []

    def run(self, name: str, args: dict[str, Any]) -> tuple[dict[str, Any], str]:
        """Execute a tool call. Returns (structured result for the trace, text for the model)."""
        if name == "calculator":
            result = self.calculator.evaluate(str(args.get("expression", "")))
        elif name in WEATHER_TOOLS and self._guessed_place(str(args.get("city", ""))):
            result = {"success": False, "error": "The user hasn't said where. Ask them which city."}
        elif name == "get_weather":
            result = self.weather.get_weather(str(args.get("city", "")), self._units(args))
        elif name == "get_forecast":
            result = self.weather.get_forecast(str(args.get("city", "")), args.get("date") or None, self._units(args))
        elif name == "get_air_quality":
            result = self.weather.get_air_quality(str(args.get("city", "")))
        elif name == "get_crypto_price":
            result = self.crypto.get_price(str(args.get("coin", "")))
        elif name == "web_search":
            result = self._web_search(str(args.get("query", "")))
        elif name == "search_documents":
            result = self._search_documents(str(args.get("query", "")), args.get("document"))
        elif name == "list_documents":
            result = {"success": True, "documents": [
                {"name": d["document_name"], "pages": d["pages"]} for d in self.rag.list_documents(self.user_id)
            ]}
        elif name == "create_reminder":
            result = self._create_reminder(str(args.get("text", "")), str(args.get("when", "")))
        elif name == "list_reminders":
            pending = self.reminders.get_reminders(self.user_id, status="pending")
            result = {"success": True, "timezone": self._tz.key, "reminders": [
                {"text": r["reminder_text"], "due": self._local(r["due_at"]) if r["due_at"] else r["scheduled_time"]}
                for r in pending[:20]
            ]}
        else:
            result = {"success": False, "error": f"Unknown tool '{name}'."}

        if result.get("success") and name in CARD_KINDS:
            self.cards.append({"tool": CARD_KINDS[name], "output": result})
        return result, self._for_model(result)

    def _guessed_place(self, city: str) -> bool:
        """Models fill in a city for "weather today" rather than ask; only a place the user gave may be looked up."""
        if not self.conversation_text or extract_city_from_query(self.message):
            return False
        return not any(word in self.conversation_text for word in re.findall(r"\w{3,}", city.lower()))

    @staticmethod
    def _units(args: dict[str, Any]) -> str:
        return "imperial" if str(args.get("units", "")).lower() in ("imperial", "fahrenheit") else "metric"

    def _create_reminder(self, text: str, when: str) -> dict[str, Any]:
        try:
            r = self.reminders.create_reminder(self.user_id, text, when, timezone=self.timezone)
        except ValueError as err:
            return {"success": False, "error": str(err)}
        # due_at (UTC) is for the UI card; the model gets local time so it doesn't announce UTC to the user
        return {"success": True, "id": r["id"], "text": r["reminder_text"], "due_at": r["due_at"],
                "due_local": self._local(r["due_at"]), "timezone": self._tz.key}

    @property
    def _tz(self) -> ZoneInfo:
        return resolve_timezone(self.timezone)

    def _local(self, iso_utc: str) -> str:
        return datetime.fromisoformat(iso_utc).astimezone(self._tz).strftime("%A %d %B %Y, %H:%M")

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

    def _scope(self, document: str | None) -> list[str] | None:
        """The named document (matched loosely: the model may drop the extension), else this chat's files."""
        if document:
            wanted = str(document).lower().removesuffix(".pdf")
            names = [d["document_name"] for d in self.rag.list_documents(self.user_id)]
            matches = [n for n in names if wanted in n.lower()]
            if matches:
                return matches
        return self.documents

    def _search_documents(self, query: str, document: str | None = None) -> dict[str, Any]:
        chunks = self.rag.retrieve(query, limit=6, user_id=self.user_id, document_names=self._scope(document))
        if not chunks:
            note = (
                "None of the user's documents mention this. Tell them it isn't in their documents; don't guess."
                if self.rag.count(self.user_id)
                else "The user hasn't uploaded any documents yet."
            )
            return {"success": True, "query": query, "passages": [], "note": note}
        passages = []
        for c in chunks:
            doc, page, text = c.get("document_name", "Document"), c.get("page_number", 1), c.get("content", "")
            # Models often search a document several times: the same passage keeps its number
            seen = next((s for s in self.sources if s.get("document") == doc and s.get("excerpt") == text), None)
            if seen:
                passages.append({"n": seen["n"], "document": doc, "page": page, "text": text})
                continue
            n = len(self.sources) + 1
            source = {"n": n, "kind": "document", "document": doc, "page": page, "excerpt": text}
            if c.get("section"):
                source["section"] = c["section"]
            self.sources.append(source)
            passages.append({"n": n, "document": doc, "page": page, "text": text})
        return {"success": True, "query": query, "passages": passages}

    @staticmethod
    def _for_model(result: dict[str, Any]) -> str:
        """Tool result as compact JSON for the model (numbered sources keep their [n])."""
        return json.dumps(result, default=str)[:MAX_RESULT_CHARS]
