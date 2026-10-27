"""Weather tool integrating with OpenWeather API."""

import logging
import re
from typing import Any

import requests

from src.backend.core.config import settings

logger = logging.getLogger(__name__)


# Time and filler phrases that can trail the place: "in Paris right now", "Berlin tomorrow please"
_TRAILING = re.compile(
    r"(?:[\s,]+(?:(?:for|at|in)\s+)?(?:right now|now|today|tonight|tomorrow|currently|at the moment|please|"
    r"this (?:morning|afternoon|evening|week|weekend)|in (?:celsius|fahrenheit)))+$",
    re.IGNORECASE,
)
# Words that are never the place, for messages without "in/for/at/of": "weather pune", "Tokyo forecast?"
_NOT_PLACE = {
    "what", "what's", "whats", "how", "how's", "is", "it", "the", "a", "like", "tell", "me", "show", "give",
    "weather", "forecast", "temperature", "temp", "climate", "conditions", "current", "currently", "outside",
    "hot", "cold", "warm", "windy", "humid", "humidity", "rain", "raining", "snow", "snowing", "sunny", "cloudy",
    "going", "to", "be", "will", "does", "do", "i", "need", "an", "umbrella", "jacket", "should", "bring",
}


def extract_city_from_query(query: str) -> str:
    """The place a weather question is about: "how hot is it in Dubai right now" -> "Dubai"."""
    text = _TRAILING.sub("", query.strip().strip("?.! \t\n")).strip()
    # The place follows the last "in / for / at / of": "is it snowing in Toronto", "weather of New York"
    matches = list(re.finditer(r"\b(?:in|for|at|of|near)\s+", text, flags=re.IGNORECASE))
    if matches:
        place = text[matches[-1].end():].strip(" ,")
        if place and place.split()[0].lower() not in _NOT_PLACE:
            return place
    # No preposition: drop the weather and question words ("weather pune", "Pune weather today")
    words = [w for w in re.split(r"\s+", text) if w.lower().strip(",") not in _NOT_PLACE]
    return " ".join(words).strip(" ,") or query.strip()


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
                logger.warning("OpenWeather error %s: %s", response.status_code, response.text[:500])
                return {
                    "success": False,
                    "error": f"Weather service returned an error (status {response.status_code}).",
                }
        except requests.RequestException as err:
            # Exception text can contain the request URL, including API keys in query params
            logger.warning("%s request failed: %s", self.__class__.__name__, type(err).__name__)
            return {
                "success": False,
                "error": "Weather service is unreachable right now.",
            }

    def run(self, query: str) -> dict[str, Any]:
        """Extract city from query and fetch weather."""
        city = extract_city_from_query(query)
        return self.get_weather(city)
