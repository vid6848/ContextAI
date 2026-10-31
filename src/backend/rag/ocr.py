"""Read scanned PDF pages: photos of paper have no text layer, so Gemini transcribes the page images."""

import base64
import logging
import re
from typing import Any

import pymupdf

from src.backend.core.config import settings
from src.backend.llm.client import completion, normalize_model_name
from src.backend.rag.structure import Block

logger = logging.getLogger(__name__)

# Below this a page is treated as having no text of its own (a stray page number on a scan)
MIN_PAGE_CHARS = 20
MAX_OCR_PAGES = 20
PAGES_PER_CALL = 4
# Readable for the model, and small enough not to matter on a 512 MB instance
OCR_DPI = 130
MAX_IMAGE_SIDE = 1600
BODY_SIZE = 11.0
_MARKER = re.compile(r"^\s*\[\[PAGE (\d+)\]\]\s*$", re.MULTILINE)
PROMPT = (
    "These are scanned pages of a document. Transcribe all the text exactly, in its original language and "
    "reading order, keeping paragraphs separated by blank lines. Write tables row by row with values separated "
    "by ' | '. Don't add comments or describe images. Start each page with a line [[PAGE n]], where n is the "
    "page number given before its image. If a page has no text, write only its [[PAGE n]] line."
)


def pages_needing_ocr(pdf_doc: Any, blocks: list[Block]) -> list[int]:
    """1-based numbers of pages with no real text that still show something (images or drawings)."""
    chars: dict[int, int] = {}
    for b in blocks:
        chars[b.page] = chars.get(b.page, 0) + len(b.text)
    return [
        n for n, page in enumerate(pdf_doc, start=1)
        if chars.get(n, 0) < MIN_PAGE_CHARS and (page.get_images() or page.get_drawings())
    ]


def _page_image(page: Any) -> str:
    zoom = min(OCR_DPI / 72, MAX_IMAGE_SIDE / max(page.rect.width, page.rect.height))
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csGRAY)
    return base64.b64encode(pixmap.tobytes("jpeg", jpg_quality=70)).decode("ascii")


def _transcribe(pdf_doc: Any, pages: list[int]) -> str:
    content: list[dict[str, Any]] = [{"type": "text", "text": PROMPT}]
    for n in pages:
        content.append({"type": "text", "text": f"Page {n}:"})
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{_page_image(pdf_doc[n - 1])}"},
        })
    messages = [{"role": "user", "content": content}]
    last_error: Exception | None = None
    for model in filter(None, (settings.model_name, settings.fallback_model_name)):
        try:
            return completion(normalize_model_name(model), messages, settings.gemini_api_key).content
        except Exception as err:  # noqa: BLE001 - the next model may still work; failure is reported to the caller
            last_error = err
    raise last_error or RuntimeError("No model configured")


def _blocks(reply: str, pages: list[int]) -> list[Block]:
    """Split a transcription on its [[PAGE n]] markers into paragraphs."""
    parts = _MARKER.split(reply)
    found = list(zip(parts[1::2], parts[2::2], strict=False)) or [(str(pages[0]), reply)]
    blocks: list[Block] = []
    for number, text in found:
        page = int(number) if int(number) in pages else pages[0]
        for paragraph in re.split(r"\n\s*\n", text):
            clean = re.sub(r"\s+", " ", paragraph).strip()
            if clean:
                blocks.append(Block(page=page, text=clean, size=BODY_SIZE, bold=False))
    return blocks


def ocr_pages(pdf_doc: Any, pages: list[int]) -> list[Block]:
    """Transcribe pages a few at a time. A failed batch is skipped so the rest of the document still works."""
    if not settings.gemini_api_key:
        return []
    blocks: list[Block] = []
    for i in range(0, len(pages), PAGES_PER_CALL):
        batch = pages[i : i + PAGES_PER_CALL]
        try:
            blocks.extend(_blocks(_transcribe(pdf_doc, batch), batch))
        except Exception:  # noqa: BLE001 - logged; the caller reports a PDF with nothing readable
            logger.exception("Couldn't read scanned pages %s", batch)
    return blocks
