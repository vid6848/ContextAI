"""Hybrid re-ranking of vector-search candidates: semantic similarity blended with keyword coverage."""

import re
from typing import Any

STOPWORDS = frozenset(
    "a an and are as at be by can could did do does for from had has have how i if in is it its me my of on or "
    "our should so that the their them there these they this to was we what when where which who why will with "
    "would you your about any into than then also just not no yes get got".split()
)

# Below both bars a candidate is treated as unrelated to the question (measured on real PDFs: relevant
# passages score cosine >= ~0.2 or share most query terms; off-topic ones sit near cosine 0).
MIN_SIMILARITY = 0.22
MIN_COVERAGE = 0.5
SEMANTIC_WEIGHT = 0.65


def terms(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w[:-1] if len(w) > 4 and w.endswith("s") else w for w in words if w not in STOPWORDS and len(w) > 1}


def similarity_from_l2(distance: float | None) -> float:
    """Chroma's default space is squared L2 over unit vectors: d = 2 - 2cos."""
    if distance is None:
        return 0.0
    return max(0.0, min(1.0, 1 - distance / 2))


def rerank(query: str, candidates: list[dict[str, Any]], limit: int, gate: bool = True) -> list[dict[str, Any]]:
    """Score candidates, drop the irrelevant ones (unless gate=False), and return the best `limit`.

    Each candidate needs "content" and "distance"; "similarity", "coverage" and "score" are added.
    """
    q_terms = terms(query)
    scored = []
    for c in candidates:
        sim = similarity_from_l2(c.get("distance"))
        coverage = len(q_terms & terms(c.get("content", ""))) / len(q_terms) if q_terms else 0.0
        if gate and sim < MIN_SIMILARITY and coverage < MIN_COVERAGE:
            continue
        score = SEMANTIC_WEIGHT * sim + (1 - SEMANTIC_WEIGHT) * coverage
        scored.append({**c, "similarity": round(sim, 3), "coverage": round(coverage, 3), "score": round(score, 3)})
    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored[:limit]
