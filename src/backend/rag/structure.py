"""Structure-aware chunking: split PDFs along headings and paragraphs instead of fixed character windows."""

import re
import statistics
from dataclasses import dataclass
from typing import Any

BOLD_FLAG = 16  # PyMuPDF span flag for bold text


@dataclass
class Block:
    page: int
    text: str
    size: float
    bold: bool


@dataclass
class Chunk:
    page: int
    heading: str | None
    text: str


def extract_blocks(pdf_doc: Any) -> list[Block]:
    """Text blocks (roughly paragraphs) with their font size and weight, in reading order."""
    blocks: list[Block] = []
    for page_idx, page in enumerate(pdf_doc, start=1):
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            spans = [s for line in block.get("lines", []) for s in line.get("spans", []) if s.get("text", "").strip()]
            if not spans:
                continue
            text = " ".join(
                "".join(s["text"] for s in line.get("spans", [])).strip() for line in block.get("lines", [])
            )
            # Postgres text can't hold NUL, which some PDF fonts emit
            text = re.sub(r"\s+", " ", text.replace("\x00", "")).strip()
            if text:
                blocks.append(Block(
                    page=page_idx,
                    text=text,
                    size=max(s.get("size", 0.0) for s in spans),
                    bold=all(s.get("flags", 0) & BOLD_FLAG for s in spans),
                ))
    return blocks


def _body_size(blocks: list[Block]) -> float:
    """Most common font size weighted by text length: the document's body text size."""
    weighted = [round(b.size, 1) for b in blocks for _ in range(max(1, len(b.text) // 40))]
    return statistics.mode(weighted) if weighted else 0.0


def is_heading(block: Block, body_size: float) -> bool:
    text = block.text
    if len(text) > 120 or (text.endswith((".", ",", ";", ":")) and len(text) > 40):
        return False
    larger = body_size and block.size >= body_size * 1.15
    return bool(larger or (block.bold and len(text) <= 80))


def _split_long(text: str, max_chars: int) -> list[str]:
    """Split an over-long paragraph on sentence boundaries."""
    if len(text) <= max_chars:
        return [text]
    parts, current = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        while len(sentence) > max_chars:  # a single run-on "sentence"
            parts.append(sentence[:max_chars])
            sentence = sentence[max_chars:]
        if current and len(current) + len(sentence) + 1 > max_chars:
            parts.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        parts.append(current)
    return parts


def structure_chunks(blocks: list[Block], max_chars: int = 900) -> list[Chunk]:
    """Group paragraphs under their nearest heading into chunks of at most ~max_chars.

    A chunk never spans a heading or a page, and each chunk records the heading it sits under so the
    passage keeps its context ("5. Expenses") even when the heading itself is in an earlier chunk.
    """
    body = _body_size(blocks)
    chunks: list[Chunk] = []
    heading: str | None = None
    buf: list[str] = []
    buf_page = blocks[0].page if blocks else 1

    def flush() -> None:
        if buf:
            chunks.append(Chunk(page=buf_page, heading=heading, text="\n\n".join(buf)))
            buf.clear()

    for b in blocks:
        if is_heading(b, body):
            flush()
            heading, buf_page = b.text, b.page
            continue
        if b.page != buf_page:
            flush()
            buf_page = b.page
        for piece in _split_long(b.text, max_chars):
            if buf and sum(len(p) for p in buf) + len(piece) > max_chars:
                flush()
            buf.append(piece)
    flush()
    return chunks


def chunk_document_text(chunk: Chunk) -> str:
    """Text stored and embedded for a chunk: its section heading plus the passage."""
    return f"{chunk.heading}\n\n{chunk.text}" if chunk.heading else chunk.text
