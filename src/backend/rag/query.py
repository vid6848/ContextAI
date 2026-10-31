"""What a question wants from a document: specific pages, the whole thing, or a semantic search."""

import re
from typing import Any

from src.backend.rag.rerank import terms

LAST_PAGE = -1
MAX_PAGE_RANGE = 20
_ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
}
_PAGE_NUMBERS = re.compile(
    r"\b(?:pages?|pg\.?|p\.)\s*(?:no\.?\s*|number\s*|#\s*)?(\d+)"
    r"(?:\s*(?:-|–|to|through|till|until)\s*(\d+))?((?:\s*(?:,|and|&)\s*\d+)*)",
    re.IGNORECASE,
)
_PAGE_ORDINAL = re.compile(r"\b(\d+)(?:st|nd|rd|th)\s+page\b|\b(" + "|".join(_ORDINALS) + r")\s+page\b", re.IGNORECASE)
_LAST = re.compile(r"\b(?:last|final)\s+page\b", re.IGNORECASE)

# A question made only of these words is about the document as a whole, not a topic inside it:
# nearest-neighbour search has nothing to match on, so passages are sampled across the file instead
_OVERVIEW_WORDS = frozenset(
    "summary summarize summarise summarization summarisation overview tldr tl dr gist recap synopsis abstract "
    "point idea takeaway highlight finding theme topic purpose conclusion introduction intro outline structure "
    "quiz flashcard question explain describe review analyze analyse analysis understand notes "
    "author wrote written writer title translate compare comparison difference similarity".split()
)
_FILLER_WORDS = frozenset(
    "document doc pdf file paper report contract handbook manual book article attachment attached upload uploaded "
    "whole entire full all each both two main key important major short brief quick detailed simple please give "
    "make create write list show tell provide bullet table saying say says mean means talk "
    "isko iska yeh ye kya hai karo batao samjhao".split()
)
_LANGUAGE_TARGET = re.compile(r"\btranslate\b.*\b(this|it|document|pdf|file)\b", re.IGNORECASE)


def requested_pages(query: str) -> list[int] | None:
    """Page numbers a question names ("page 3", "pages 2-4", "last page"), or None. LAST_PAGE stands for the end."""
    pages: list[int] = []
    for match in _PAGE_NUMBERS.finditer(query):
        start = int(match[1])
        end = int(match[2]) if match[2] else start
        pages.extend(range(start, min(end, start + MAX_PAGE_RANGE) + 1))
        pages.extend(int(n) for n in re.findall(r"\d+", match[3] or ""))
    for match in _PAGE_ORDINAL.finditer(query):
        pages.append(int(match[1]) if match[1] else _ORDINALS[match[2].lower()])
    if _LAST.search(query):
        pages.append(LAST_PAGE)
    return pages or None


def is_overview(query: str, document_names: list[str] | None = None) -> bool:
    """True for "summarize this", "key points of report.pdf"; False for "summarize the refund policy"."""
    if _LANGUAGE_TARGET.search(query):
        return True
    words = terms(query)
    if not words:
        return True  # "what is this about": nothing but pronouns
    named = terms(" ".join(document_names or []))
    return bool(words & _OVERVIEW_WORDS) and not (words - _OVERVIEW_WORDS - _FILLER_WORDS - named)


def pick_pages(passages: list[dict[str, Any]], pages: list[int], limit: int) -> list[dict[str, Any]]:
    """The passages on the requested pages of each document (in order)."""
    last_page: dict[str, int] = {}
    for p in passages:
        last_page[p["document_name"]] = max(last_page.get(p["document_name"], 0), p["page_number"])
    wanted = [
        p for p in passages
        if p["page_number"] in pages or (LAST_PAGE in pages and p["page_number"] == last_page[p["document_name"]])
    ]
    return wanted[:limit]


def spread(passages: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Up to `limit` passages evenly across each document, always with its start and end."""
    by_document: dict[str, list[dict[str, Any]]] = {}
    for p in passages:
        by_document.setdefault(p["document_name"], []).append(p)
    share = max(2, limit // max(len(by_document), 1))
    chosen: list[dict[str, Any]] = []
    for rows in by_document.values():
        if len(rows) <= share:
            chosen.extend(rows)
            continue
        step = (len(rows) - 1) / (share - 1)
        chosen.extend(rows[round(i * step)] for i in range(share))
    return chosen
