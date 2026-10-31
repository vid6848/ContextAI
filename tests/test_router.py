"""Tests for the hybrid router: precision of the fast path on the labelled eval set, and its guards."""

import pytest

from evals.route_eval import evaluate, load
from src.backend.classifier.intent_classifier import IntentClassifier
from src.backend.classifier.router import HybridRouter, looks_multi_part, tools_mentioned
from src.backend.core.config import settings


@pytest.fixture(scope="module")
def router():
    classifier = IntentClassifier()
    classifier.train()
    return HybridRouter(classifier)


def test_fast_path_is_precise_and_useful_at_the_configured_threshold(router):
    """Regression guard for routing quality: wrong fast-path picks break answers, so precision comes first."""
    result = evaluate(router, load(), settings.hybrid_confidence_threshold)
    assert result["fast_path_precision"] >= 0.95, result["mistakes"]
    assert result["fast_path_share"] >= 0.35


@pytest.mark.parametrize(
    ("text", "multi"),
    [
        ("what's the weather in paris and the price of bitcoin", True),
        ("how much is 3 btc in dollars", True),
        ("compare eth and sol prices", True),
        ("price of bitcoin", False),
        ("weather in Tokyo?", False),
        ("weather in rome and in tokyo", True),
        ("is it raining in London and what's the temperature in Delhi", True),
    ],
)
def test_multi_part_guard(text, multi):
    intent = "CRYPTO" if "WEATHER" not in tools_mentioned(text) or "btc" in text else "WEATHER"
    assert looks_multi_part(text, intent) is multi


def test_reminders_always_go_to_the_model(router):
    decision = router.decide("remind me to call mom tomorrow at 6", min_similarity=0.0)
    assert decision.route == "llm" and decision.reason == "needs the reminder tools"


def test_simple_requests_take_the_fast_path(router):
    cases = [("what's bitcoin trading at", "CRYPTO"), ("what's the weather in london right now", "WEATHER")]
    for text, intent in cases:
        decision = router.decide(text, settings.hybrid_confidence_threshold)
        assert (decision.route, decision.intent) == ("classifier", intent)
