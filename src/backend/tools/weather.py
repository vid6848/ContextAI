"""Weather tool integrating with OpenWeather API."""

import re
from typing import Any
import requests
from src.backend.core.config import settings


def extract_city_from_query(query: str) -> str:
    """Extract city or location name from a natural language query."""
    cleaned = query.strip()
    # Patterns like "weather in Tokyo", "weather for Paris, France", "forecast in New York"
    patterns = [
        r"(?:weather|forecast|temperature|temp|climate)\s+(?:in|for|at|of)\s+([A-Za-z\s,\.-]+)",
        r"(?:what\s+is\s+the\s+weather\s+like\s+in)\s+([A-Za-z\s,\.-]+)",
        r"([A-Za-z\s,\.-]+)\s+weather",
    ]
    for pattern in patterns:
        match = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if match:
            city = match.group(1).strip("?.! \t\n")
            if city:
                return city

    # Fallback: remove leading query words
    cleaned = re.sub(
        r"^(?:what\s+is|what's|how\s+is|tell\s+me)\s+(?:the\s+)?(?:weather|forecast|temperature)\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip("?.! \t\n")
    return cleaned or query.strip()


class WeatherTool:
    """Tool for fetching real-time weather information from OpenWeather."""

    name: str = "weather"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else settings.openweather_api_key
        self.base_url = "https://api.openweathermap.org/data/2.5/weather"

    def get_weather(self, city: str, units: str = "metric") -> dict[str, Any]:
        """Fetch current weather data for a given city name."""
        city_name = city.strip()
        if not city_name:
            return {"success": False, "error": "City name cannot be empty"}

        if not self.api_key:
            return {
                "success": False,
                "error": "OpenWeather API key is not configured in settings (OPENWEATHER_API_KEY).",
            }

        try:
            params = {
                "q": city_name,
                "appid": self.api_key,
                "units": units,
            }
            response = requests.get(self.base_url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                weather_info = data.get("weather", [{}])[0]
                main_info = data.get("main", {})
                wind_info = data.get("wind", {})
                sys_info = data.get("sys", {})

                country = sys_info.get("country", "")
                location = f"{data.get('name', city_name)}, {country}".strip(", ")

                return {
                    "success": True,
                    "location": location,
                    "temperature": main_info.get("temp"),
                    "feels_like": main_info.get("feels_like"),
                    "humidity": main_info.get("humidity"),
                    "condition": weather_info.get("main"),
                    "description": weather_info.get("description"),
                    "wind_speed": wind_info.get("speed"),
                    "units": "celsius" if units == "metric" else "fahrenheit",
                }
            elif response.status_code == 404:
                return {
                    "success": False,
                    "error": f"City '{city_name}' not found.",
                }
            else:
                return {
                    "success": False,
                    "error": f"OpenWeather API error (status {response.status_code}): {response.text}",
                }
        except requests.RequestException as err:
            return {
                "success": False,
                "error": f"Weather network request failed: {err}",
            }

    def run(self, query: str) -> dict[str, Any]:
        """Extract city from query and fetch weather."""
        city = extract_city_from_query(query)
        return self.get_weather(city)
