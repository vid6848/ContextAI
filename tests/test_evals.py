"""Tests for the eval suite's scoring rules (evals/run.py) and its labelled data."""

import pytest

from evals.run import FLOORS, check, has_facts, load, markdown, percentiles, tools_ok

TOOLS = {"calculator", "get_weather", "get_crypto_price", "web_search", "create_reminder", "list_reminders",
         "search_documents"}


@pytest.mark.parametrize(
    ("called", "ok"),
    [({"web_search"}, True), ({"web_search", "get_weather"}, True), ({"get_weather"}, False), (set(), False),
     ({"web_search", "calculator"}, False)],
)
def test_tool_choice_needs_the_required_tools_and_allows_only_optional_extras(called, ok):
    row = {"tools": ["web_search"], "optional": ["get_weather"]}
    assert tools_ok(called, row) is ok


def test_no_tool_expected_means_no_tool_called():
    assert tools_ok(set(), {"tools": []}) and not tools_ok({"web_search"}, {"tools": []})


def test_facts_ignore_case_and_thousands_separators_and_accept_alternatives():
    assert has_facts("2^16 is 65,536.", ["65536"])
    assert has_facts("You get Six Months of probation", [["6 months", "six months"]])
    assert not has_facts("Core hours start at 10:00", ["10:00", "15:00"])


def test_percentiles():
    assert percentiles([5, 1, 3, 2, 4]) == {"p50_ms": 3, "p95_ms": 5}
    assert percentiles([]) == {"p50_ms": 0.0, "p95_ms": 0.0}


def test_labelled_data_is_complete():
    rows, questions = load("intent_eval.jsonl"), load("rag_eval.jsonl")
    assert len(rows) >= 100 and len(questions) >= 25
    for row in rows:
        assert set(row["tools"]) | set(row.get("optional", [])) <= TOOLS, row
    assert all(q["facts"] for q in questions if q["section"])


def test_check_reports_metrics_below_their_floor():
    results = {"routing": {}, "retrieval": {}}
    for (section, metric), floor in FLOORS.items():
        results[section][metric] = floor
    assert check(results) == []
    results["retrieval"]["mrr"] = 0.1
    assert check(results) == [f"retrieval.mrr = 0.1 (floor {FLOORS['retrieval', 'mrr']})"]


def test_markdown_renders_offline_results():
    latency = {"p50_ms": 1.0, "p95_ms": 2.0}
    results = {
        "routing": {"requests": 100, "classifier_tool_accuracy": 0.7, "fast_path_share": 0.4,
                    "fast_path_precision": 0.98, "classifier_latency": latency, "decision_latency": latency},
        "retrieval": {"questions": 25, "hit_at_1": 1.0, "hit_at_4": 1.0, "mrr": 1.0, "gated_unanswerable": 0.0,
                      "latency": latency},
    }
    text = markdown(results)
    assert "| TF-IDF classifier only | 70% |" in text and "hit@4) | 100% |" in text
