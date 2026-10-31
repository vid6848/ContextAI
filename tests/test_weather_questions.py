"""Weather questions as people type them: finding the place, the time and the units, and OpenWeather's quirks."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.backend.agent.toolbox import ToolBox
from src.backend.tools.weather import (
    WeatherTool,
    _place_params,
    extract_city_from_query,
    extract_units,
    is_plain_current_weather,
)


@pytest.mark.parametrize("question, city", [
    ("weather in Paris", "Paris"),
    ("pune weather", "pune"),
    ("what's the weather like in New York City right now", "New York City"),
    ("forecast for Delhi on Friday", "Delhi"),
    ("what will the temperature be in Berlin at 5pm", "Berlin"),
    ("should I carry an umbrella to Bangalore tomorrow", "Bangalore"),
    ("what was the weather in Paris yesterday", "Paris"),
    ("weather at the Eiffel Tower", "Eiffel Tower"),
    ("weather in Miami in F", "Miami"),
    ("temperature in Pune in fahrenheit", "Pune"),
    ("weather in London this weekend", "London"),
])
def test_finds_the_place(question, city):
    assert extract_city_from_query(question) == city


@pytest.mark.parametrize("question", [
    "Weather", "what's the weather", "weather today", "will it rain tomorrow", "how's the weather here",
    "what's the weather where I live", "is it cold outside",
])
def test_no_place_named_means_no_guess(question):
    assert extract_city_from_query(question) == ""
    assert not is_plain_current_weather(question)


@pytest.mark.parametrize("question, plain", [
    ("weather in Paris", True),
    ("how hot is Dubai", True),
    ("will it rain in Mumbai tomorrow", False),
    ("forecast for Delhi on Friday", False),
    ("what was the weather in Paris yesterday", False),
    ("best time to visit Paris weather wise", False),
])
def test_only_right_now_questions_skip_the_model(question, plain):
    assert is_plain_current_weather(question) is plain


def test_units():
    assert extract_units("temperature in Pune in fahrenheit") == "imperial"
    assert extract_units("weather in Pune") == "metric"


@pytest.mark.parametrize("name, first", [
    ("NYC", {"q": "New York City"}),
    ("LA", {"q": "Los Angeles"}),
    ("India", {"q": "New Delhi,IN"}),  # OpenWeather's "India" is a town in Italy
    ("90210", {"zip": "90210,us"}),  # its q=90210 is a village in Mexico
    ("411001", {"zip": "411001,in"}),
    ("Springfield, IL", {"q": "Springfield,IL,US"}),
])
def test_names_openweather_misreads(name, first):
    assert next(_place_params(name)) == first


def test_trailing_country_is_retried():
    assert {"q": "Tokyo,JP"} in list(_place_params("Tokyo Japan"))
    assert {"q": "Dubai,AE"} in list(_place_params("Dubai UAE"))


def _response(status, body=None):
    return MagicMock(status_code=status, json=lambda: body or {}, text="")


@patch("src.backend.tools.weather.requests.get")
def test_second_spelling_is_used_after_404(get):
    get.side_effect = [_response(404), _response(404), _response(200, {"name": "Dubai", "sys": {"country": "AE"}})]
    assert WeatherTool(api_key="k").get_weather("Dubai UAE")["location"] == "Dubai, AE"


@patch("src.backend.tools.weather.requests.get")
def test_network_blip_is_retried(get):
    get.side_effect = [requests.Timeout(), _response(200, {"name": "Pune", "sys": {"country": "IN"}})]
    assert WeatherTool(api_key="k").get_weather("Pune")["success"]


@patch("src.backend.tools.weather.requests.get")
def test_timeout_on_an_alternative_spelling_is_not_an_outage(get):
    get.side_effect = [_response(404), requests.Timeout(), requests.Timeout()]
    result = WeatherTool(api_key="k").get_weather("Eiffel Tower")
    assert result["needs_place"] and "not found" in result["error"]


@patch("src.backend.tools.weather.requests.get", side_effect=requests.Timeout())
def test_outage_reported_as_outage(_):
    result = WeatherTool(api_key="k").get_weather("Pune")
    assert "unreachable" in result["error"] and "needs_place" not in result


def _forecast_body(tomorrow_rain=0.6):
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    steps = [
        {
            "dt": int((start + timedelta(hours=3 * i)).timestamp()),
            "main": {"temp": 20 + i % 8},
            "weather": [{"main": "Rain", "description": "light rain"}],
            "pop": tomorrow_rain if i == 8 else 0.1,
        }
        for i in range(40)
    ]
    return {"city": {"name": "Pune", "country": "IN", "timezone": 0}, "list": steps}


@patch("src.backend.tools.weather.requests.get")
def test_forecast_days_and_one_day_detail(get):
    get.return_value = _response(200, _forecast_body())
    tool = WeatherTool(api_key="k")
    forecast = tool.get_forecast("Pune")
    assert forecast["location"] == "Pune, IN" and len(forecast["days"]) >= 5
    assert forecast["days"][0]["high"] >= forecast["days"][0]["low"]
    assert "hours" not in forecast

    tomorrow = (datetime.now(UTC) + timedelta(days=1)).date().isoformat()
    one_day = tool.get_forecast("Pune", tomorrow)
    assert [d["date"] for d in one_day["days"]] == [tomorrow]
    assert one_day["hours"] and one_day["hours"][0]["rain_chance_percent"] >= 0


@patch("src.backend.tools.weather.requests.get")
def test_forecast_outside_its_range_says_so(get):
    get.return_value = _response(200, _forecast_body())
    tool = WeatherTool(api_key="k")
    far = (datetime.now(UTC) + timedelta(days=30)).date().isoformat()
    assert "only reaches" in tool.get_forecast("Pune", far)["error"]
    assert "no past weather" in tool.get_forecast("Pune", "2020-01-01")["error"]
    assert "isn't a date" in tool.get_forecast("Pune", "friday")["error"]


@patch("src.backend.tools.weather.requests.get")
def test_air_quality(get):
    get.side_effect = [
        _response(200, {"name": "Delhi", "sys": {"country": "IN"}, "coord": {"lat": 28.6, "lon": 77.2}}),
        _response(200, {"list": [{"main": {"aqi": 4}, "components": {"pm2_5": 80.1}}]}),
    ]
    result = WeatherTool(api_key="k").get_air_quality("Delhi")
    assert (result["aqi"], result["aqi_label"]) == (4, "Poor")
    assert result["pollutants_ug_m3"]["pm2_5"] == 80.1


def _toolbox(message, conversation=""):
    weather = MagicMock()
    weather.get_weather.return_value = {"success": True, "location": "x"}
    box = ToolBox(
        calculator=MagicMock(), weather=weather, crypto=MagicMock(), web=MagicMock(), rag=MagicMock(),
        reminders=MagicMock(), user_id="u", message=message, conversation_text=f"{message} {conversation}",
    )
    return box, weather


def test_model_cannot_invent_a_place():
    box, weather = _toolbox("weather today")
    result, _ = box.run("get_weather", {"city": "Pune"})
    assert "which city" in result["error"]
    weather.get_weather.assert_not_called()


@pytest.mark.parametrize("message, conversation, city", [
    ("how's the weather here", "the user lives in Ahmedabad", "Ahmedabad"),
    ("and tomorrow?", "weather in Pune", "Pune"),
    ("pune ka mausam kaisa hai", "", "Pune"),
    ("weather at the Eiffel Tower", "", "Paris"),  # the question names a place, the model resolves it
])
def test_places_the_user_gave_are_allowed(message, conversation, city):
    box, weather = _toolbox(message, conversation)
    assert box.run("get_weather", {"city": city})[0]["success"]
    weather.get_weather.assert_called_once()
