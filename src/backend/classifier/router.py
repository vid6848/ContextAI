"""Hybrid router: decide whether a request can take the fixed single-tool fast path or needs the LLM agent.

The fast path skips a model planning round, so it must only be used when it's almost certainly right.
Two independent classifiers must agree (TF-IDF + logistic regression, and nearest-neighbour search over
MiniLM sentence embeddings of the same examples), the embedding match must be strong, and the message
must not mention a second tool. Measured on evals/intent_eval.jsonl (see evals/route_eval.py).
"""

import re
from dataclasses import dataclass

import numpy as np

from src.backend.classifier.intent_classifier import IntentClassifier, get_default_training_data
from src.backend.tools.weather import is_plain_current_weather

# Intents the fast path can't serve: reminders need the reminder tools
LLM_ONLY_INTENTS = {"REMINDER"}

# Vocabulary that signals a tool. If a message touches a second tool's vocabulary, it's multi-part.
TOOL_VOCAB = {
    "WEATHER": r"\b(weather|rain|raining|temperature|snow|snowing|forecast|humid|humidity|windy|wind|sunny|cloudy|"
    r"jacket|umbrella|hot|cold|aqi|air quality|pollution|sunrise|sunset|mausam|barish|baarish)\b",
    "CRYPTO": r"\b(bitcoin|btc|eth|ethereum|crypto|solana|sol|doge|dogecoin|xrp|cardano|ada|coin|coins)\b",
    "CALCULATOR": r"(\d\s*[-+*/x^%]\s*\d|\bpercent\b|%|\bcalculate\b|\bcompute\b|\bmultiply\b|\bdivide\b|\bplus\b|"
    r"\bminus\b|\btimes\b|\bpower of\b|\bsquare\b|\bin (dollars|usd|inr|rupees|euros?|fahrenheit|celsius)\b)",
    "REMINDER": r"\b(remind|reminder|reminders|don't let me forget)\b",
    "WEB_SEARCH": r"\b(search|look up|google|news|latest|recent)\b",
    "DOCUMENT": r"\b(pdf|document|report|contract|handbook|manual|uploaded|file)\b",
}
_COINS = r"\b(bitcoin|btc|eth|ethereum|solana|sol|doge|dogecoin|xrp|cardano|ada)\b"
_COIN_ALIASES = {"btc": "bitcoin", "eth": "ethereum", "sol": "solana", "doge": "dogecoin", "ada": "cardano"}


def tools_mentioned(text: str) -> set[str]:
    return {name for name, pattern in TOOL_VOCAB.items() if re.search(pattern, text, re.IGNORECASE)}


def looks_multi_part(text: str, intent: str) -> bool:
    """A second tool's vocabulary, two coins or places, or a comparison all need more than one tool call."""
    if tools_mentioned(text) - {intent}:
        return True
    if intent == "WEATHER" and re.search(r"\b(and|or)\b", text, re.IGNORECASE):
        return True  # "weather in Rome and Tokyo": the weather node looks up one place
    coins = {_COIN_ALIASES.get(c.lower(), c.lower()) for c in re.findall(_COINS, text, re.IGNORECASE)}
    return len(coins) > 1 or bool(re.search(r"\b(compare|versus|vs\.?)\b", text, re.IGNORECASE))


@dataclass
class RouteDecision:
    intent: str
    confidence: float  # embedding similarity of the best match (0..1)
    route: str  # "classifier" (fast path) or "llm"
    reason: str


class HybridRouter:
    def __init__(self, classifier: IntentClassifier, embed=None) -> None:
        self.classifier = classifier
        if embed is None:
            from src.backend.db.embeddings import get_embedder

            embed = get_embedder()  # the same MiniLM instance the memory and document stores use
        self.embed = embed
        texts, labels = get_default_training_data()
        self.labels = np.array(labels)
        self.classes = sorted(set(labels))
        self.examples = self._normalise(np.array(self.embed(texts), dtype=np.float32))

    @staticmethod
    def _normalise(m: np.ndarray) -> np.ndarray:
        return m / np.clip(np.linalg.norm(m, axis=-1, keepdims=True), 1e-9, None)

    def nearest_intent(self, text: str) -> tuple[str, float]:
        """Intent whose 3 closest examples are most similar to the text, with that mean cosine similarity."""
        q = self._normalise(np.array(self.embed([text]), dtype=np.float32))[0]
        sims = self.examples @ q
        best = max(self.classes, key=lambda c: np.sort(sims[self.labels == c])[-3:].mean())
        return best, float(np.sort(sims[self.labels == best])[-3:].mean())

    def decide(self, text: str, min_similarity: float) -> RouteDecision:
        tfidf_intent = self.classifier.predict(text).intent
        embed_intent, similarity = self.nearest_intent(text)
        if embed_intent != tfidf_intent:
            return RouteDecision(tfidf_intent, similarity, "llm", "classifiers disagree")
        if embed_intent in LLM_ONLY_INTENTS:
            return RouteDecision(embed_intent, similarity, "llm", "needs the reminder tools")
        if looks_multi_part(text, embed_intent):
            return RouteDecision(embed_intent, similarity, "llm", "asks for more than one thing")
        if similarity < min_similarity:
            return RouteDecision(embed_intent, similarity, "llm", "not confident enough")
        if embed_intent == "WEATHER" and not is_plain_current_weather(text):
            return RouteDecision(embed_intent, similarity, "llm", "needs a place or a forecast")
        return RouteDecision(embed_intent, similarity, "classifier", "both classifiers agree")
