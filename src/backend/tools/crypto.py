"""Crypto price tool integrating with CoinGecko API."""

import re
from typing import Any
import requests

# Common cryptocurrency symbol to CoinGecko ID mapping
_COIN_MAPPING = {
    "btc": "bitcoin",
    "bitcoin": "bitcoin",
    "eth": "ethereum",
    "ethereum": "ethereum",
    "sol": "solana",
    "solana": "solana",
    "doge": "dogecoin",
    "dogecoin": "dogecoin",
    "ada": "cardano",
    "cardano": "cardano",
    "xrp": "ripple",
    "ripple": "ripple",
    "dot": "polkadot",
    "polkadot": "polkadot",
    "avax": "avalanche-2",
    "avalanche": "avalanche-2",
    "link": "chainlink",
    "chainlink": "chainlink",
    "bnb": "binancecoin",
    "binance": "binancecoin",
    "matic": "matic-network",
    "polygon": "matic-network",
    "usdt": "tether",
    "tether": "tether",
    "usdc": "usd-coin",
}


def extract_coin_from_query(query: str) -> str:
    """Extract cryptocurrency symbol or name from natural language query."""
    cleaned = query.strip().lower()

    # Direct keyword search against known coins
    words = re.findall(r"\b[a-z0-9\-]+\b", cleaned)
    for word in words:
        if word in _COIN_MAPPING:
            return _COIN_MAPPING[word]

    # Pattern matches like "price of <coin>" or "<coin> price"
    patterns = [
        r"(?:price\s+of|value\s+of|cost\s+of|how\s+much\s+is)\s+([a-z0-9\-]+)",
        r"([a-z0-9\-]+)\s+(?:price|value|usd|quote)",
    ]
    for pattern in patterns:
        match = re.search(pattern, cleaned)
        if match:
            candidate = match.group(1).strip()
            return _COIN_MAPPING.get(candidate, candidate)

    return "bitcoin"  # default fallback


class CryptoTool:
    """Tool for fetching real-time cryptocurrency prices from CoinGecko."""

    name: str = "crypto"

    def __init__(self, base_url: str = "https://api.coingecko.com/api/v3") -> None:
        self.base_url = base_url

    def get_price(self, coin_id: str) -> dict[str, Any]:
        """Fetch cryptocurrency price and market data for a given coin ID."""
        coin = coin_id.strip().lower()
        # Resolve symbol if mapped
        resolved_id = _COIN_MAPPING.get(coin, coin)

        if not resolved_id:
            return {"success": False, "error": "Coin identifier cannot be empty"}

        try:
            url = f"{self.base_url}/simple/price"
            params = {
                "ids": resolved_id,
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_market_cap": "true",
            }
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if resolved_id not in data:
                    return {
                        "success": False,
                        "error": f"Cryptocurrency '{resolved_id}' not found.",
                    }

                coin_data = data[resolved_id]
                return {
                    "success": True,
                    "coin": resolved_id,
                    "price_usd": coin_data.get("usd"),
                    "change_24h_percent": round(coin_data.get("usd_24h_change", 0.0), 2)
                    if coin_data.get("usd_24h_change") is not None
                    else None,
                    "market_cap_usd": coin_data.get("usd_market_cap"),
                }
            elif response.status_code == 429:
                return {
                    "success": False,
                    "error": "CoinGecko API rate limit reached. Please try again shortly.",
                }
            else:
                return {
                    "success": False,
                    "error": f"CoinGecko API error (status {response.status_code}): {response.text}",
                }
        except requests.RequestException as err:
            return {
                "success": False,
                "error": f"Crypto network request failed: {err}",
            }

    def run(self, query: str) -> dict[str, Any]:
        """Extract coin identifier from natural query and fetch price."""
        coin_id = extract_coin_from_query(query)
        return self.get_price(coin_id)
