"""Measure the hybrid router on evals/intent_eval.jsonl.

    python -m evals.route_eval [min_similarity ...]

Reports how many requests take the single-tool fast path and how often that choice is right. Multi-part
requests are labelled MULTI: the fast path can never serve them, so any that leak count as errors.
"""

import json
import sys
from pathlib import Path

from src.backend.classifier.intent_classifier import IntentClassifier
from src.backend.classifier.router import HybridRouter

EVAL_FILE = Path(__file__).with_name("intent_eval.jsonl")


def load() -> list[dict]:
    return [json.loads(line) for line in EVAL_FILE.read_text().splitlines() if line.strip()]


def evaluate(router: HybridRouter, rows: list[dict], min_similarity: float) -> dict:
    fast = correct = 0
    mistakes = []
    for row in rows:
        decision = router.decide(row["text"], min_similarity)
        if decision.route == "classifier":
            fast += 1
            if decision.intent == row["intent"]:
                correct += 1
            else:
                mistakes.append((row["text"], row["intent"], decision.intent))
    return {
        "min_similarity": min_similarity,
        "fast_path_share": fast / len(rows),
        "fast_path_precision": correct / fast if fast else 1.0,
        "mistakes": mistakes,
    }


def main() -> None:
    thresholds = [float(t) for t in sys.argv[1:]] or [0.3, 0.35, 0.4, 0.45, 0.5]
    classifier = IntentClassifier()
    classifier.train()
    router = HybridRouter(classifier)
    rows = load()
    single = [r for r in rows if r["intent"] != "MULTI"]
    tfidf_acc = sum(classifier.predict(r["text"]).intent == r["intent"] for r in single) / len(single)
    print(f"{len(rows)} labelled requests; TF-IDF alone: {tfidf_acc:.0%} accurate")
    for t in thresholds:
        r = evaluate(router, rows, t)
        print(f"min_similarity {t:.2f}: fast path {r['fast_path_share']:.0%}, precision {r['fast_path_precision']:.0%}")
        for text, want, got in r["mistakes"]:
            print(f"    ✗ {text!r}: expected {want}, routed {got}")


if __name__ == "__main__":
    main()
