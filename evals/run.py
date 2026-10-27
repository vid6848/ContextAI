"""ContextAI evaluation suite.

    python -m evals.run               # offline: routing and retrieval quality + latency (no API key needed)
    python -m evals.run --online      # also tool choice by function calling, answer correctness, and RAG
                                      # faithfulness/relevance judged by the model (needs GEMINI_API_KEY)

--check exits 1 when an offline metric drops below its floor (CI runs this on every push and PR).
--json / --markdown write the results; CI adds the markdown to the job summary.

Data: evals/intent_eval.jsonl (100 requests labelled with intent, the tools the model should call first,
tools that are fine but optional, and facts a correct answer contains) and evals/rag_eval.jsonl (25 questions
about the handbook in evals/rag_fixture.py, 3 of which it doesn't answer).
"""

import argparse
import json
import re
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

EVALS = Path(__file__).parent

# Offline floors for --check: deterministic, so any drop is a real regression
FLOORS = {
    ("routing", "fast_path_precision"): 0.95,
    ("routing", "fast_path_share"): 0.35,
    ("routing", "classifier_tool_accuracy"): 0.70,
    ("retrieval", "hit_at_4"): 0.90,
    ("retrieval", "mrr"): 0.80,
}

# Tools the classifier path runs for each intent (reminders and memory have no tool node there)
CLASSIFIER_TOOLS = {"CALCULATOR": {"calculator"}, "WEATHER": {"get_weather"}, "CRYPTO": {"get_crypto_price"},
                    "WEB_SEARCH": {"web_search"}, "DOCUMENT": {"search_documents"}}

JUDGE_PROMPT = """You grade an assistant's answer to a question about a document. The assistant could only use \
the numbered passages below.

Question: {question}

Passages:
{passages}

Answer: {answer}

Reply with JSON only, no prose: {{"faithful": true|false, "relevant": true|false, "abstained": true|false}}
- faithful: every factual claim in the answer is supported by the passages (saying the passages don't cover \
the question counts as faithful)
- relevant: the answer addresses the question that was asked
- abstained: the answer says the document doesn't contain this information"""


def load(name: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (EVALS / name).read_text().splitlines() if line.strip()]


def ms(seconds: float) -> float:
    return round(seconds * 1000, 1)


def percentiles(samples: list[float]) -> dict[str, float]:
    if not samples:
        return {"p50_ms": 0.0, "p95_ms": 0.0}
    ordered = sorted(samples)
    return {"p50_ms": round(statistics.median(ordered), 1),
            "p95_ms": round(ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))], 1)}


def tools_ok(called: set[str], row: dict[str, Any]) -> bool:
    """Right first move: every required tool, and nothing beyond the required and optional ones."""
    required = set(row["tools"])
    return required <= called <= required | set(row.get("optional", []))


def _normalize(text: str) -> str:
    return re.sub(r"(?<=\d)[,  ](?=\d{3})", "", text).lower()


def has_facts(answer: str, facts: list[str | list[str]]) -> bool:
    """Each fact (or one of its alternatives) appears in the answer; thousands separators are ignored."""
    text = _normalize(answer)
    return all(any(_normalize(alt) in text for alt in ([f] if isinstance(f, str) else f)) for f in facts)


def rate(values: list[bool]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


# ---------------------------------------------------------------- offline


def eval_routing(rows: list[dict[str, Any]]) -> dict[str, Any]:
    from src.backend.classifier.intent_classifier import IntentClassifier
    from src.backend.classifier.router import HybridRouter
    from src.backend.core.config import settings

    classifier = IntentClassifier()
    classifier.train()
    router = HybridRouter(classifier)
    router.decide("warm up", settings.hybrid_confidence_threshold)  # loads the embedding model

    timings, tfidf_timings, details = [], [], []
    for row in rows:
        started = time.perf_counter()
        decision = router.decide(row["text"], settings.hybrid_confidence_threshold)
        timings.append(ms(time.perf_counter() - started))
        started = time.perf_counter()
        predicted = classifier.predict(row["text"]).intent
        tfidf_timings.append(ms(time.perf_counter() - started))
        details.append({
            "text": row["text"], "label": row["intent"], "tfidf": predicted, "route": decision.route,
            "intent": decision.intent, "classifier_tools": sorted(CLASSIFIER_TOOLS.get(predicted, set())),
        })

    single = [d for d in details if d["label"] != "MULTI"]
    fast = [d for d in details if d["route"] == "classifier"]
    pairs = zip(details, rows, strict=True)
    return {
        "requests": len(rows),
        "tfidf_intent_accuracy": rate([d["tfidf"] == d["label"] for d in single]),
        "classifier_tool_accuracy": rate([tools_ok(set(d["classifier_tools"]), r) for d, r in pairs]),
        "fast_path_share": rate([d["route"] == "classifier" for d in details]),
        "fast_path_precision": rate([d["intent"] == d["label"] for d in fast]),
        "fast_path_mistakes": [d["text"] for d in fast if d["intent"] != d["label"]],
        "classifier_latency": percentiles(tfidf_timings),
        "decision_latency": percentiles(timings),
        "details": details,
    }


def build_pipeline(workdir: Path) -> Any:
    from evals.rag_fixture import DOCUMENT_NAME, handbook_pdf
    from src.backend.rag.pipeline import DocumentRAGPipeline

    pdf = workdir / DOCUMENT_NAME
    pdf.write_bytes(handbook_pdf())
    pipeline = DocumentRAGPipeline(persist_dir=str(workdir / "chroma"), collection_name="eval_docs")
    pipeline.ingest_pdf(str(pdf), user_id="eval", document_name=DOCUMENT_NAME)
    return pipeline


def eval_retrieval(pipeline: Any, questions: list[dict[str, Any]]) -> dict[str, Any]:
    """What the search_documents tool returns: top 4 passages, with unrelated ones gated out."""
    pipeline.retrieve("warm up", limit=4, user_id="eval")
    hits1, hits4, ranks, abstained, timings, misses = [], [], [], [], [], []
    for q in questions:
        started = time.perf_counter()
        chunks = pipeline.retrieve(q["question"], limit=4, user_id="eval")
        timings.append(ms(time.perf_counter() - started))
        sections = [c.get("section") for c in chunks]
        if q["section"] is None:
            abstained.append(not chunks)
            continue
        rank = sections.index(q["section"]) + 1 if q["section"] in sections else None
        hits1.append(rank == 1)
        hits4.append(rank is not None)
        ranks.append(1 / rank if rank else 0.0)
        if rank != 1:
            misses.append({"question": q["question"], "expected": q["section"], "got": sections})
    return {
        "questions": len(questions),
        "hit_at_1": rate(hits1),
        "hit_at_4": rate(hits4),
        "mrr": round(sum(ranks) / len(ranks), 3),
        "gated_unanswerable": rate(abstained),
        "latency": percentiles(timings),
        "misses": misses,
    }


# ---------------------------------------------------------------- online


def throttle(rpm: int) -> None:
    """Space out model calls to stay under the API's requests-per-minute limit."""
    import litellm

    real, lock, last = litellm.completion, threading.Lock(), [0.0]

    def paced(*args: Any, **kwargs: Any) -> Any:
        with lock:
            wait = last[0] + 60 / rpm - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            last[0] = time.monotonic()
        return real(*args, **kwargs)

    litellm.completion = paced


def eval_tool_choice(rows: list[dict[str, Any]], routing: dict[str, Any]) -> dict[str, Any]:
    """First model round with every tool available, as in the shipped agent; tools are not executed."""
    from src.backend.agent.graph import build_chat_messages
    from src.backend.agent.toolbox import TOOL_SPECS
    from src.backend.llm.client import LLMClient

    llm = LLMClient()
    llm_ok, hybrid_ok, timings, mistakes = [], [], [], []
    for row, decision in zip(rows, routing["details"], strict=True):
        started = time.perf_counter()
        try:
            message: dict[str, Any] = {}
            for kind, payload in llm.chat_round(build_chat_messages({"message": row["text"]}), tools=TOOL_SPECS):
                if kind == "message":
                    message = payload
            called = {c["function"]["name"] for c in message.get("tool_calls") or []}
        except Exception as err:  # counted as a miss, reported below
            called = {f"error: {type(err).__name__}"}
        timings.append(ms(time.perf_counter() - started))
        ok = tools_ok(called, row)
        llm_ok.append(ok)
        if not ok:
            mistakes.append({"text": row["text"], "expected": row["tools"], "called": sorted(called)})
        if decision["route"] == "classifier":
            hybrid_ok.append(tools_ok(CLASSIFIER_TOOLS.get(decision["intent"], set()), row))
        else:
            hybrid_ok.append(ok)
    return {
        "llm_tool_accuracy": rate(llm_ok),
        "hybrid_tool_accuracy": rate(hybrid_ok),
        "tool_round_latency": percentiles(timings),
        "mistakes": mistakes,
    }


def eval_answers(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Full agent turns (function calling, real calculator) for requests with a known answer."""
    from src.backend.agent.graph import get_agent_app
    from src.backend.core.config import settings

    settings.router_mode = "llm"
    agent = get_agent_app()
    correct, timings, wrong = [], [], []
    for row in [r for r in rows if r.get("facts")]:
        started = time.perf_counter()
        try:
            answer = agent.invoke({"message": row["text"], "user_id": "eval"}).get("response", "")
        except Exception as err:
            answer = f"error: {type(err).__name__}"
        timings.append(ms(time.perf_counter() - started))
        ok = has_facts(answer, row["facts"])
        correct.append(ok)
        if not ok:
            wrong.append({"text": row["text"], "facts": row["facts"], "answer": answer[:300]})
    return {"questions": len(correct), "fact_accuracy": rate(correct), "turn_latency": percentiles(timings),
            "wrong": wrong}


def _judge(llm: Any, question: str, passages: str, answer: str) -> dict[str, bool]:
    prompt = JUDGE_PROMPT.format(question=question, passages=passages, answer=answer)
    raw = llm.generate_response([{"role": "user", "content": prompt}], temperature=0)
    match = re.search(r"\{.*\}", raw, re.S)
    try:
        verdict = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        verdict = {}
    return {k: bool(verdict.get(k)) for k in ("faithful", "relevant", "abstained")}


def eval_rag_answers(pipeline: Any, questions: list[dict[str, Any]]) -> dict[str, Any]:
    """Questions asked with the handbook attached (the app's 'ask about this PDF' flow), graded by the model."""
    from evals.rag_fixture import DOCUMENT_NAME
    from src.backend.agent.graph import get_agent_app
    from src.backend.llm.client import LLMClient

    agent = get_agent_app(rag_pipeline=pipeline)
    judge = LLMClient()
    facts, faithful, relevant, abstained, timings, notes = [], [], [], [], [], []
    for q in questions:
        started = time.perf_counter()
        try:
            result = agent.invoke({"message": q["question"], "user_id": "eval", "attachments": [DOCUMENT_NAME]})
            answer = result.get("response", "")
            sources = result.get("rag_sources") or []
            passages = "\n\n".join(f"[{s['n']}] {s.get('excerpt', '')}" for s in sources)
            timings.append(ms(time.perf_counter() - started))
            verdict = _judge(judge, q["question"], passages, answer)
        except Exception as err:
            answer, verdict = f"error: {type(err).__name__}", {"faithful": False, "relevant": False, "abstained": False}
        faithful.append(verdict["faithful"])
        if q["section"] is None:
            abstained.append(verdict["abstained"])
            ok = verdict["abstained"]
        else:
            relevant.append(verdict["relevant"])
            facts.append(has_facts(answer, q["facts"]))
            ok = facts[-1] and verdict["faithful"] and verdict["relevant"]
        if not ok:
            notes.append({"question": q["question"], "answer": answer[:300], **verdict})
    return {
        "fact_recall": rate(facts),
        "faithfulness": rate(faithful),
        "answer_relevance": rate(relevant),
        "abstains_when_not_covered": rate(abstained),
        "turn_latency": percentiles(timings),
        "notes": notes,
    }


# ---------------------------------------------------------------- report


def pct(value: float) -> str:
    return f"{value:.0%}"


def markdown(results: dict[str, Any]) -> str:
    r, d = results["routing"], results["retrieval"]
    online = results.get("tool_choice")
    lines = [
        f"### Tool routing ({r['requests']} labelled requests)", "",
        "| Router | Picks the right tools | Model calls to decide | Decision latency p50 / p95 |",
        "|---|---|---|---|",
        f"| TF-IDF classifier only | {pct(r['classifier_tool_accuracy'])} | 0 | "
        f"{r['classifier_latency']['p50_ms']} / {r['classifier_latency']['p95_ms']} ms |",
    ]
    if online:
        lat = online["tool_round_latency"]
        llm_calls = round(r["requests"] * (1 - r["fast_path_share"]))
        lines += [
            f"| Gemini function calling only | {pct(online['llm_tool_accuracy'])} | {r['requests']} | "
            f"{lat['p50_ms']:.0f} / {lat['p95_ms']:.0f} ms |",
            f"| **Hybrid (shipped)** | **{pct(online['hybrid_tool_accuracy'])}** | {llm_calls} | "
            f"{r['decision_latency']['p50_ms']} ms on the fast path, else plus a model call |",
        ]
    lines += [
        "",
        f"Hybrid fast path: TF-IDF and MiniLM embeddings must agree and be confident; it handles "
        f"{pct(r['fast_path_share'])} of requests without a model call, {pct(r['fast_path_precision'])} of them "
        f"correctly (decision p50 / p95: {r['decision_latency']['p50_ms']} / {r['decision_latency']['p95_ms']} ms).",
        "",
        f"### Document Q&A ({d['questions']} questions about a 10-section handbook, 3 not covered by it)", "",
        "| Metric | Result |", "|---|---|",
        f"| Right passage ranked first (hit@1) | {pct(d['hit_at_1'])} |",
        f"| Right passage in the top 4 (hit@4) | {pct(d['hit_at_4'])} |",
        f"| Mean reciprocal rank | {d['mrr']:.2f} |",
        f"| Off-topic questions gated (no passages returned) | {pct(d['gated_unanswerable'])} |",
        f"| Retrieval latency p50 / p95 | {d['latency']['p50_ms']} / {d['latency']['p95_ms']} ms |",
    ]
    if rag := results.get("rag_answers"):
        lines += [
            f"| Answers containing the expected facts | {pct(rag['fact_recall'])} |",
            f"| Faithfulness (every claim supported by the passages, model-judged) | {pct(rag['faithfulness'])} |",
            f"| Answer relevance (model-judged) | {pct(rag['answer_relevance'])} |",
            f"| Says so when the document doesn't cover it | {pct(rag['abstains_when_not_covered'])} |",
            f"| Full answer latency p50 / p95 | {rag['turn_latency']['p50_ms']:.0f} / "
            f"{rag['turn_latency']['p95_ms']:.0f} ms |",
        ]
    if ans := results.get("answers"):
        lines += [
            "", f"### Answer correctness ({ans['questions']} requests with a known answer, full agent turns)", "",
            f"Correct: **{pct(ans['fact_accuracy'])}**, latency p50 / p95: {ans['turn_latency']['p50_ms']:.0f} / "
            f"{ans['turn_latency']['p95_ms']:.0f} ms.",
        ]
    if model := results.get("model"):
        lines += ["", f"Model: `{model}`."]
    return "\n".join(lines) + "\n"


def check(results: dict[str, Any]) -> list[str]:
    return [
        f"{section}.{metric} = {results[section][metric]} (floor {floor})"
        for (section, metric), floor in FLOORS.items()
        if results[section][metric] < floor
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--online", action="store_true", help="also run the model-based evals")
    parser.add_argument("--rpm", type=int, default=30, help="max model calls per minute (online)")
    parser.add_argument("--check", action="store_true", help="exit 1 if an offline metric is below its floor")
    parser.add_argument("--json", type=Path, help="write all results here")
    parser.add_argument("--markdown", type=Path, help="write the summary table here")
    args = parser.parse_args()

    from src.backend.core.config import settings

    workdir = Path(tempfile.mkdtemp(prefix="contextai-evals-"))
    # Never touch real data: local stores in a temp dir, no tracing, verbatim memory (no extra model calls)
    settings.database_url = ""
    settings.sqlite_db_path = str(workdir / "eval.db")
    settings.chroma_persist_dir = str(workdir / "chroma-memory")
    settings.memory_mode = "heuristic"
    settings.langfuse_public_key = settings.langfuse_secret_key = ""

    rows, questions = load("intent_eval.jsonl"), load("rag_eval.jsonl")
    results: dict[str, Any] = {"routing": eval_routing(rows)}
    pipeline = build_pipeline(workdir)
    results["retrieval"] = eval_retrieval(pipeline, questions)

    if args.online:
        if not settings.gemini_api_key:
            print("--online needs GEMINI_API_KEY", file=sys.stderr)
            return 2
        throttle(args.rpm)
        results["model"] = settings.model_name
        results["tool_choice"] = eval_tool_choice(rows, results["routing"])
        results["answers"] = eval_answers(rows)
        results["rag_answers"] = eval_rag_answers(pipeline, questions)

    summary = markdown(results)
    print(summary)
    for section in ("tool_choice", "answers", "rag_answers"):
        for key in ("mistakes", "wrong", "notes"):
            for item in (results.get(section) or {}).get(key, []):
                print(f"  ✗ [{section}] {json.dumps(item, ensure_ascii=False)}")
    if args.json:
        results["routing"].pop("details")
        args.json.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    if args.markdown:
        args.markdown.write_text(summary)
    if args.check and (failures := check(results)):
        print("Below floor:\n  " + "\n  ".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
