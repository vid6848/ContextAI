"""Web search tool integrating with Tavily API."""

from typing import Any
import requests
from src.backend.core.config import settings


class TavilySearchTool:
    """Tool for real-time web search powered by the Tavily API."""

    name: str = "web_search"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else settings.tavily_api_key
        self.base_url = "https://api.tavily.com/search"

    def search(self, query: str, max_results: int = 4) -> dict[str, Any]:
        """Perform a web search for the given query."""
        search_query = query.strip()
        if not search_query:
            return {"success": False, "error": "Search query cannot be empty"}

        if not self.api_key:
            return {
                "success": False,
                "error": "Tavily API key is not configured in settings (TAVILY_API_KEY).",
            }

        try:
            payload = {
                "api_key": self.api_key,
                "query": search_query,
                "search_depth": "basic",
                "max_results": max_results,
            }
            response = requests.post(self.base_url, json=payload, timeout=12)
            if response.status_code == 200:
                data = response.json()
                raw_results = data.get("results", [])
                structured_results = [
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "content": item.get("content", ""),
                    }
                    for item in raw_results
                ]
                return {
                    "success": True,
                    "query": search_query,
                    "results": structured_results,
                }
            else:
                return {
                    "success": False,
                    "error": f"Tavily search API error (status {response.status_code}): {response.text}",
                }
        except requests.RequestException as err:
            return {
                "success": False,
                "error": f"Web search network request failed: {err}",
            }

    def run(self, query: str) -> dict[str, Any]:
        """Execute web search for the user query."""
        return self.search(query)
