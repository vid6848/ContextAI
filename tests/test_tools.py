"""Tests for Calculator, Weather, Crypto, and Tavily web search tools."""

from unittest.mock import patch, MagicMock
from src.backend.tools.calculator import CalculatorTool, extract_math_expression
from src.backend.tools.weather import WeatherTool, extract_city_from_query
from src.backend.tools.crypto import CryptoTool, extract_coin_from_query
from src.backend.tools.web_search import TavilySearchTool


# ============================================================================
# Calculator Tool Tests
# ============================================================================

def test_calculator_basic_arithmetic():
    """Verify safe calculator evaluates basic arithmetic correctly."""
    calc = CalculatorTool()

    assert calc.evaluate("2 + 2")["result"] == 4
    assert calc.evaluate("10 - 4")["result"] == 6
    assert calc.evaluate("6 * 7")["result"] == 42
    assert calc.evaluate("15 / 3")["result"] == 5
    assert calc.evaluate("2 ** 5")["result"] == 32
    assert calc.evaluate("(10 + 5) * 2 - 4")["result"] == 26


def test_calculator_invalid_input_and_errors():
    """Verify calculator handles division by zero and unsafe/invalid input."""
    calc = CalculatorTool()

    # Division by zero
    div_zero = calc.evaluate("10 / 0")
    assert not div_zero["success"]
    assert "Division by zero" in div_zero["error"]

    # Empty expression
    empty_res = calc.evaluate("")
    assert not empty_res["success"]

    # Unsafe function call / import attempt
    unsafe_call = calc.evaluate("__import__('os').system('ls')")
    assert not unsafe_call["success"]

    # Syntax error
    syntax_err = calc.evaluate("5 + * 3")
    assert not syntax_err["success"]


def test_calculator_natural_language_queries():
    """Verify calculator extracts and evaluates expression from natural language."""
    calc = CalculatorTool()

    assert extract_math_expression("calculate 25 * 4") == "25 * 4"
    assert extract_math_expression("what is 100 / 4?") == "100 / 4"

    res = calc.run("calculate 12 * 12")
    assert res["success"]
    assert res["result"] == 144


# ============================================================================
# Weather Tool Tests
# ============================================================================

def test_extract_city_from_query():
    """Verify city extraction from weather queries."""
    assert "tokyo" in extract_city_from_query("What is the weather in Tokyo?").lower()
    assert "paris" in extract_city_from_query("weather for Paris").lower()


@patch("src.backend.tools.weather.requests.get")
def test_weather_tool_success_mocked(mock_get):
    """Verify weather tool parses successful OpenWeather response."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "name": "London",
        "sys": {"country": "GB"},
        "main": {"temp": 16.5, "feels_like": 15.8, "humidity": 72},
        "weather": [{"main": "Clouds", "description": "scattered clouds"}],
        "wind": {"speed": 3.6},
    }
    mock_get.return_value = mock_resp

    tool = WeatherTool(api_key="mock_weather_key")
    result = tool.get_weather("London")

    assert result["success"]
    assert result["location"] == "London, GB"
    assert result["temperature"] == 16.5
    assert result["condition"] == "Clouds"
    assert result["humidity"] == 72


def test_weather_tool_missing_api_key():
    """Verify weather tool returns clear error when API key is unconfigured."""
    tool = WeatherTool(api_key="")
    result = tool.get_weather("London")
    assert not result["success"]
    assert "API key is not configured" in result["error"]


@patch("src.backend.tools.weather.requests.get")
def test_weather_tool_city_not_found(mock_get):
    """Verify weather tool handles 404 city not found."""
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_get.return_value = mock_resp

    tool = WeatherTool(api_key="mock_weather_key")
    result = tool.get_weather("Atlantis")
    assert not result["success"]
    assert "not found" in result["error"]


# ============================================================================
# Crypto Tool Tests
# ============================================================================

def test_extract_coin_from_query():
    """Verify cryptocurrency identification from natural language queries."""
    assert extract_coin_from_query("What is the price of Bitcoin?") == "bitcoin"
    assert extract_coin_from_query("Check BTC price") == "bitcoin"
    assert extract_coin_from_query("How much is ETH?") == "ethereum"
    assert extract_coin_from_query("Solana usd quote") == "solana"


@patch("src.backend.tools.crypto.requests.get")
def test_crypto_tool_success_mocked(mock_get):
    """Verify crypto tool parses CoinGecko price data."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "bitcoin": {
            "usd": 68500.0,
            "usd_24h_change": 3.45,
            "usd_market_cap": 1350000000000,
        }
    }
    mock_get.return_value = mock_resp

    tool = CryptoTool()
    result = tool.get_price("btc")

    assert result["success"]
    assert result["coin"] == "bitcoin"
    assert result["price_usd"] == 68500.0
    assert result["change_24h_percent"] == 3.45
    assert result["market_cap_usd"] == 1350000000000


@patch("src.backend.tools.crypto.requests.get")
def test_crypto_tool_rate_limit(mock_get):
    """Verify crypto tool handles 429 rate limit gracefully."""
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_get.return_value = mock_resp

    tool = CryptoTool()
    result = tool.get_price("ethereum")
    assert not result["success"]
    assert "rate limit" in result["error"]


# ============================================================================
# Tavily Web Search Tool Tests
# ============================================================================

@patch("src.backend.tools.web_search.requests.post")
def test_tavily_search_success_mocked(mock_post):
    """Verify Tavily web search tool parses structured search results."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "query": "Python 3.13 features",
        "results": [
            {
                "title": "What's New In Python 3.13",
                "url": "https://docs.python.org/3.13/whatsnew/3.13.html",
                "content": "Python 3.13 features free-threaded CPython and a new interactive interpreter.",
            }
        ],
    }
    mock_post.return_value = mock_resp

    tool = TavilySearchTool(api_key="mock_tavily_key")
    result = tool.search("Python 3.13 features")

    assert result["success"]
    assert result["query"] == "Python 3.13 features"
    assert len(result["results"]) == 1
    assert result["results"][0]["title"] == "What's New In Python 3.13"
    assert "free-threaded" in result["results"][0]["content"]


def test_tavily_search_missing_api_key():
    """Verify Tavily tool returns error when API key is missing."""
    tool = TavilySearchTool(api_key="")
    result = tool.search("Python news")
    assert not result["success"]
    assert "API key is not configured" in result["error"]
