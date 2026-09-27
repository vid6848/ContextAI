"""Tests for TF-IDF + Logistic Regression intent classifier."""

import pytest
from src.backend.classifier.intent_classifier import (
    IntentClassifier,
    PredictionResult,
    SUPPORTED_INTENTS,
    get_default_training_data,
)


def test_default_training_dataset_structure():
    """Verify default training dataset covers all 8 supported intents."""
    texts, labels = get_default_training_data()
    assert len(texts) == len(labels)
    assert len(texts) > 0

    unique_intents = set(labels)
    assert unique_intents == set(SUPPORTED_INTENTS)
    assert len(unique_intents) == 8


def test_classifier_training_and_is_trained():
    """Verify classifier can be trained and marks is_trained flag."""
    classifier = IntentClassifier()
    assert not classifier.is_trained

    classifier.train()
    assert classifier.is_trained


def test_classifier_prediction_output_format():
    """Verify prediction returns PredictionResult with intent and valid confidence."""
    classifier = IntentClassifier()
    classifier.train()

    result = classifier.predict("What is the current temperature in Seattle?")
    assert isinstance(result, PredictionResult)
    assert isinstance(result.intent, str)
    assert isinstance(result.confidence, float)
    assert 0.0 <= result.confidence <= 1.0

    # Verify tuple unpacking compatibility
    intent, confidence = result
    assert intent == result.intent
    assert confidence == result.confidence


@pytest.mark.parametrize(
    "query, expected_intent",
    [
        ("What is the weather forecast for tomorrow?", "WEATHER"),
        ("What is the current price of Bitcoin?", "CRYPTO"),
        ("Search the web for recent artificial intelligence news", "WEB_SEARCH"),
        ("Calculate 25 multiplied by 40", "CALCULATOR"),
        ("Remember that my favorite programming language is Python", "MEMORY"),
        ("Summarize the attached PDF contract document", "DOCUMENT"),
        ("Remind me to call the doctor tomorrow at 10 AM", "REMINDER"),
        ("Hello there, how are you today?", "GENERAL"),
    ],
)
def test_classifier_predictions_across_intents(query: str, expected_intent: str):
    """Verify accurate predictions for typical queries representing each intent."""
    classifier = IntentClassifier()
    classifier.train()

    result = classifier.predict(query)
    assert result.intent == expected_intent
    assert result.confidence > 0.20


def test_classifier_evaluation_metrics():
    """Verify evaluation returns accuracy, precision, recall, f1, and confusion matrix."""
    classifier = IntentClassifier()
    metrics = classifier.evaluate(test_size=0.25, random_state=42)

    assert "accuracy" in metrics
    assert "precision" in metrics
    assert "recall" in metrics
    assert "f1_score" in metrics
    assert "confusion_matrix" in metrics
    assert "labels" in metrics

    # Verify metric score ranges
    assert 0.0 <= metrics["accuracy"] <= 1.0
    assert 0.0 <= metrics["precision"] <= 1.0
    assert 0.0 <= metrics["recall"] <= 1.0
    assert 0.0 <= metrics["f1_score"] <= 1.0

    # Realistic benchmark assertions for student project
    assert metrics["accuracy"] >= 0.75
    assert metrics["f1_score"] >= 0.75

    # Check confusion matrix dimensions (8x8)
    cm = metrics["confusion_matrix"]
    assert len(cm) == 8
    for row in cm:
        assert len(row) == 8


def test_classifier_custom_training():
    """Verify classifier can be trained on a custom mini dataset."""
    classifier = IntentClassifier()
    custom_texts = [
        ("rain and storm", "WEATHER"),
        ("sunny warm skies", "WEATHER"),
        ("bitcoin ethereum", "CRYPTO"),
        ("doge btc price", "CRYPTO"),
    ]
    texts = [t[0] for t in custom_texts]
    labels = [t[1] for t in custom_texts]

    classifier.train(texts, labels)
    result = classifier.predict("forecast rain")
    assert result.intent == "WEATHER"


def test_classifier_invalid_training_data():
    """Verify classifier raises ValueError on mismatched texts and labels."""
    classifier = IntentClassifier()
    with pytest.raises(ValueError, match="match"):
        classifier.train(texts=["hello"], labels=["GENERAL", "WEATHER"])

    with pytest.raises(ValueError, match="empty"):
        classifier.train(texts=[], labels=[])
