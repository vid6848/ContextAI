"""Train the intent classifier on its default data and write the weights the server loads.

    python -m scripts.export_intent_model

Run after changing DEFAULT_TRAINING_DATA; tests/test_classifier.py fails while the file is out of date.
"""

from src.backend.classifier.intent_classifier import MODEL_FILE, IntentClassifier


def main() -> None:
    classifier = IntentClassifier()
    classifier.train()
    classifier.export()
    print(f"Wrote {MODEL_FILE} ({len(classifier.params['vocabulary'])} terms)")


if __name__ == "__main__":
    main()
