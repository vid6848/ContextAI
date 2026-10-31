"""Weather tool integrating with OpenWeather: current conditions, 5-day forecast and air quality."""

import logging
import re
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

import requests

from src.backend.core.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.openweathermap.org/data/2.5"
# OpenWeather's free forecast covers 5 days in 3-hour steps
MAX_FORECAST_DAYS = 5
REQUEST_TIMEOUT = (4, 8)  # connect, read
AQI_LABELS = {1: "Good", 2: "Fair", 3: "Moderate", 4: "Poor", 5: "Very poor"}

_WHEN = (
    r"right now|now|today|tonight|tomorrow|yesterday|currently|at the moment|later|please|"
    r"(?:this|next|last|coming)\s+(?:morning|afternoon|evening|night|week|weekend|month|"
    r"mon|tues|wednes|thurs|fri|satur|sun)(?:day)?|"
    r"(?:mon|tues|wednes|thurs|fri|satur|sun)day(?:\s+(?:morning|afternoon|evening|night))?|"
    r"(?:tomorrow|today)\s+(?:morning|afternoon|evening|night)|"
    r"(?:the\s+)?(?:next\s+)?\d+\s+days?|\d{1,2}(?::\d{2})?\s*(?:am|pm)|noon|midnight|"
    r"in (?:celsius|fahrenheit|c|f)|weather[- ]wise"
)
# Time and filler phrases that can trail the place: "in Paris right now", "Delhi on Friday", "Berlin at 5pm"
_TRAILING = re.compile(rf"(?:[\s,]+(?:(?:for|at|in|on|by)\s+)?(?:the\s+)?(?:{_WHEN}))+$", re.IGNORECASE)
# Anything but "now": the current-conditions endpoint can't answer these
_NOT_NOW = re.compile(
    r"\b(tomorrow|tonight|yesterday|forecast|later|weekend|next|last|coming|"
    r"(?:mon|tues|wednes|thurs|fri|satur|sun)day|\d+[- ]days?|\d{1,2}(?::\d{2})?\s*(?:am|pm)|"
    r"(?:this|tomorrow) (?:morning|afternoon|evening|night|week)|will|going to|gonna|"
    r"best time|usually|typical(?:ly)?|average|seasons?|climate)\b",
    re.IGNORECASE,
)
# "here", "my city": only memory or the conversation can say where that is
_RELATIVE_PLACE = re.compile(
    r"\b(here|there|home|outside|my (?:city|town|area|place|location|home)|this (?:city|town|area)|"
    r"where i|around me|near me|nearby|local)\b",
    re.IGNORECASE,
)
# Words that are never the place, for messages without "in/for/at/of": "weather pune", "Tokyo forecast?"
_NOT_PLACE = {
    "what", "what's", "whats", "how", "how's", "hows", "is", "it", "the", "a", "like", "tell", "me", "show", "give",
    "weather", "forecast", "temperature", "temp", "climate", "conditions", "current", "currently", "outside",
    "hot", "cold", "warm", "windy", "humid", "humidity", "rain", "raining", "snow", "snowing", "sunny", "cloudy",
    "going", "to", "be", "will", "does", "do", "i", "need", "an", "umbrella", "jacket", "should", "bring",
    "carry", "take", "wear", "get", "was", "wind", "speed", "best", "time", "visit", "my", "this", "that",
    "where", "here", "there", "today", "tonight", "tomorrow", "now", "please", "live", "stay", "you", "can",
    "check", "report", "update", "looking", "look", "s", "and", "or", "am", "are", "much", "very",
}
# Names OpenWeather can't resolve or resolves wrongly ("India" is a town in Italy to it)
_ALIASES = {
    "nyc": "New York City", "ny": "New York City", "la": "Los Angeles", "sf": "San Francisco", "dc": "Washington DC",
    "uk": "London,GB", "united kingdom": "London,GB", "england": "London,GB", "india": "New Delhi,IN",
    "usa": "Washington DC", "us": "Washington DC", "america": "Washington DC", "united states": "Washington DC",
    "china": "Beijing,CN", "japan": "Tokyo,JP", "germany": "Berlin,DE", "france": "Paris,FR", "italy": "Rome,IT",
    "spain": "Madrid,ES", "canada": "Ottawa,CA", "australia": "Canberra,AU", "russia": "Moscow,RU",
    "brazil": "Brasilia,BR", "uae": "Dubai,AE", "pakistan": "Islamabad,PK", "singapore": "Singapore,SG",
}
_US_STATE = re.compile(r"^(.+?),?\s+([A-Z]{2})$")
_US_STATES = frozenset(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK "
    "OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
)


def extract_units(query: str) -> str:
    """"weather in Miami in fahrenheit" -> imperial; metric otherwise."""
    return "imperial" if re.search(r"\b(fahrenheit|in f)\b|°\s*f\b", query, re.IGNORECASE) else "metric"


def extract_city_from_query(query: str) -> str:
    """The place a weather question names: "how hot is it in Dubai right now" -> "Dubai". Empty if it names none."""
    text = _TRAILING.sub("", query.strip().strip("?.! \t\n")).strip()
    if _RELATIVE_PLACE.search(text):
        return ""
    # The place follows the last "in / for / at / of": "is it snowing in Toronto", "weather of New York"
    matches = list(re.finditer(r"\b(?:in|for|at|of|near|to)\s+", text, flags=re.IGNORECASE))
    if matches:
        place = re.sub(r"^the\s+", "", text[matches[-1].end():], flags=re.IGNORECASE).strip(" ,")
        if place and place.split()[0].lower() not in _NOT_PLACE:
            return place
    # No preposition: drop the weather and question words ("weather pune", "Pune weather today")
    words = [w for w in text.split() if w.lower().strip(",") not in _NOT_PLACE]
    return " ".join(words).strip(" ,") if len(words) <= 3 else ""


def is_plain_current_weather(query: str) -> bool:
    """A named place and no other time than now: the only question the classifier fast path can answer alone."""
    return bool(extract_city_from_query(query)) and not _NOT_NOW.search(query)


def _place_params(city: str) -> Iterator[dict[str, str]]:
    """OpenWeather query parameters to try for a place name, most likely first."""
    name = re.sub(r"\s+", " ", city).strip()
    if re.fullmatch(r"\d{5}", name):
        yield {"zip": f"{name},us"}
    if re.fullmatch(r"\d{6}", name):
        yield {"zip": f"{name},in"}
    if alias := _ALIASES.get(name.lower().strip(".")):
        yield {"q": alias}
    if (state := _US_STATE.match(name)) and state[2] in _US_STATES:
        yield {"q": f"{state[1]},{state[2]},US"}  # "Springfield, IL" only resolves with the country
    yield {"q": name}
    # "Tokyo Japan", "Dubai UAE": a trailing region it can't parse. Only the leading name is the city.
    words = name.replace(",", " ").split()
    if 1 < len(words) <= 3:
        if "," in (country := _ALIASES.get(words[-1].lower(), "")):
            yield {"q": f"{' '.join(words[:-1])},{country.split(',')[-1]}"}
        yield {"q": " ".join(words[:-1])}


def _get(url: str, params: dict[str, Any]) -> requests.Response:
    """GET with one retry: a brief network blip shouldn't cost the user an answer."""
    try:
        return requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        return requests.get(url, params=params, timeout=REQUEST_TIMEOUT)


def _clock(unix_time: int | None, offset: int) -> str | None:
    if unix_time is None:
        return None
    return datetime.fromtimestamp(unix_time + offset, UTC).strftime("%H:%M")


class WeatherTool:
    """Tool for fetching real-time weather information from OpenWeather."""

    name: str = "weather"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else settings.openweather_api_key
        self.base_url = f"{BASE_URL}/weather"

    def _fetch(self, url: str, city: str, units: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """GET an endpoint for a place, trying its other spellings on 404. Returns (data, error result)."""
        city_name = city.strip()
        if not city_name:
            return None, {"success": False, "error": "City name cannot be empty", "needs_place": True}
        if not self.api_key:
            return None, {
                "success": False,
                "error": "OpenWeather API key is not configured in settings (OPENWEATHER_API_KEY).",
            }
        not_found: dict[str, Any] = {"success": False, "error": f"City '{city_name}' not found.", "needs_place": True}
        for attempt, place in enumerate(_place_params(city_name)):
            try:
                response = _get(url, {**place, "appid": self.api_key, "units": units})
            except requests.RequestException as err:
                # Exception text can contain the request URL, including API keys in query params
                logger.warning("%s request failed: %s", self.__class__.__name__, type(err).__name__)
                # The service already answered about this place: this was only an alternative spelling
                return None, not_found if attempt else {
                    "success": False,
                    "error": "Weather service is unreachable right now.",
                }
            if response.status_code == 200:
                return response.json(), None
            if response.status_code != 404:
                logger.warning("OpenWeather error %s: %s", response.status_code, response.text[:500])
                return None, {
                    "success": False,
                    "error": f"Weather service returned an error (status {response.status_code}).",
                }
        return None, not_found

    def get_weather(self, city: str, units: str = "metric") -> dict[str, Any]:
        """Fetch current weather data for a given city name."""
        data, error = self._fetch(self.base_url, city, units)
        if error or data is None:
            return error or {}
        weather_info = (data.get("weather") or [{}])[0]
        main_info = data.get("main", {})
        wind_info = data.get("wind", {})
        sys_info = data.get("sys", {})
        offset = data.get("timezone") or 0
        country = sys_info.get("country", "")
        return {
            "success": True,
            "location": f"{data.get('name', city.strip())}, {country}".strip(", "),
            "temperature": main_info.get("temp"),
            "feels_like": main_info.get("feels_like"),
            "humidity": main_info.get("humidity"),
            "condition": weather_info.get("main"),
            "description": weather_info.get("description"),
            "wind_speed": wind_info.get("speed"),
            "units": "celsius" if units == "metric" else "fahrenheit",
            "clouds_percent": (data.get("clouds") or {}).get("all"),
            "visibility_m": data.get("visibility"),
            "sunrise": _clock(sys_info.get("sunrise"), offset),
            "sunset": _clock(sys_info.get("sunset"), offset),
            "local_time": _clock(data.get("dt"), offset),
        }

    def get_forecast(self, city: str, day: str | None = None, units: str = "metric") -> dict[str, Any]:
        """Daily forecast for the next 5 days, plus 3-hour steps when `day` (YYYY-MM-DD) is given."""
        target: date | None = None
        if day:
            try:
                target = date.fromisoformat(day.strip()[:10])
            except ValueError:
                return {"success": False, "error": f"'{day}' isn't a date; use YYYY-MM-DD."}
        data, error = self._fetch(f"{BASE_URL}/forecast", city, units)
        if error or data is None:
            return error or {}

        place = data.get("city", {})
        tz = timezone(timedelta(seconds=place.get("timezone") or 0))
        by_day: dict[date, list[dict[str, Any]]] = {}
        for step in data.get("list") or []:
            by_day.setdefault(datetime.fromtimestamp(step["dt"], tz).date(), []).append(step)
        if not by_day:
            return {"success": False, "error": "The weather service returned no forecast."}

        today = datetime.now(tz).date()
        last = max(by_day)
        if target and target < today:
            return {"success": False, "error": "OpenWeather has no past weather, only now and the next 5 days."}
        if target and target > last:
            return {
                "success": False,
                "error": f"The forecast only reaches {last.isoformat()} ({MAX_FORECAST_DAYS} days ahead).",
            }
        days = [self._day_summary(d, steps) for d, steps in sorted(by_day.items())]
        if target:
            days = [d for d in days if d["date"] == target.isoformat()]
        result: dict[str, Any] = {
            "success": True,
            "location": f"{place.get('name', city.strip())}, {place.get('country', '')}".strip(", "),
            "units": "celsius" if units == "metric" else "fahrenheit",
            "today": today.isoformat(),
            "days": days,
        }
        if target:
            result["hours"] = [
                {
                    "time": datetime.fromtimestamp(s["dt"], tz).strftime("%H:%M"),
                    "temperature": s.get("main", {}).get("temp"),
                    "description": (s.get("weather") or [{}])[0].get("description"),
                    "rain_chance_percent": round((s.get("pop") or 0) * 100),
                }
                for s in by_day.get(target, [])
            ]
        return result

    @staticmethod
    def _day_summary(day: date, steps: list[dict[str, Any]]) -> dict[str, Any]:
        temps = [s["main"]["temp"] for s in steps if "temp" in s.get("main", {})]
        conditions = [(s.get("weather") or [{}])[0] for s in steps]
        # The condition at midday says more about the day than the one at 3am
        typical = conditions[len(conditions) // 2]
        return {
            "date": day.isoformat(),
            "weekday": day.strftime("%A"),
            "high": max(temps, default=None),
            "low": min(temps, default=None),
            "condition": typical.get("main"),
            "description": typical.get("description"),
            "rain_chance_percent": round(max((s.get("pop") or 0) for s in steps) * 100),
        }

    def get_air_quality(self, city: str) -> dict[str, Any]:
        """Current air quality: OpenWeather's 1-5 index and the main pollutants."""
        data, error = self._fetch(self.base_url, city, "metric")
        if error or data is None:
            return error or {}
        coord = data.get("coord") or {}
        try:
            response = _get(
                f"{BASE_URL}/air_pollution", {"lat": coord.get("lat"), "lon": coord.get("lon"), "appid": self.api_key}
            )
        except requests.RequestException as err:
            logger.warning("%s request failed: %s", self.__class__.__name__, type(err).__name__)
            return {"success": False, "error": "Weather service is unreachable right now."}
        if response.status_code != 200:
            logger.warning("OpenWeather error %s: %s", response.status_code, response.text[:500])
            return {"success": False, "error": f"Weather service returned an error (status {response.status_code})."}
        reading = (response.json().get("list") or [{}])[0]
        aqi = reading.get("main", {}).get("aqi")
        country = data.get("sys", {}).get("country", "")
        return {
            "success": True,
            "location": f"{data.get('name', city.strip())}, {country}".strip(", "),
            "aqi": aqi,
            "aqi_scale": "1 (good) to 5 (very poor)",
            "aqi_label": AQI_LABELS.get(aqi),
            "pollutants_ug_m3": reading.get("components"),
        }

    def run(self, query: str) -> dict[str, Any]:
        """Extract the place from a raw question and answer it from the matching endpoint."""
        city, units = extract_city_from_query(query), extract_units(query)
        return self.get_weather(city, units) if not _NOT_NOW.search(query) else self.get_forecast(city, units=units)
