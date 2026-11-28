"""Page furniture: running headers and footers that repeat on many pages, bare page numbers, and "Página X de Y". They
are not content, and indexed they make every chunk of a document look alike.

Options: ``min_pages`` (default 3) and ``min_share`` (default 0.3): a short block whose text, with digits masked,
repeats on at least that many pages and that share of the document is furniture; ``max_chars`` (default 140) keeps
real paragraphs out of the comparison."""
from __future__ import annotations

import re
from collections import defaultdict

from ..model import NormalizedDocument
from ..registry import STEPS, register
from .base import Step, dropped

PAGE_OF = re.compile(r"\b(?:p[áa]gina|p[áa]g\.?|page)\s*\d+\s*(?:de|of|/)\s*\d+\b", re.IGNORECASE)
BARE_PAGE = re.compile(r"^\s*(?:[-–]\s*)?(?:p[áa]g(?:ina)?\.?\s*)?\d{1,4}(?:\s*[-–])?\s*$", re.IGNORECASE)


def _key(text: str) -> str:
    return re.sub(r"\d+", "#", text.lower()).strip()


@register(STEPS, "furniture")
class FurnitureStep(Step):
    name = "furniture"

    def __call__(self, doc: NormalizedDocument) -> NormalizedDocument:
        max_chars = int(self.options.get("max_chars", 140))
        pages_by_key: dict[str, set[int]] = defaultdict(set)
        for b in doc.blocks:
            if b.page is not None and b.kind != "table" and len(b.text) <= max_chars:
                pages_by_key[_key(b.text)].add(b.page)
        n_pages = doc.pages or len({b.page for b in doc.blocks if b.page is not None}) or 1
        threshold = max(int(self.options.get("min_pages", 3)), float(self.options.get("min_share", 0.3)) * n_pages)
        repeated = {k for k, pages in pages_by_key.items() if len(pages) >= threshold}

        kept, removed = [], []
        for b in doc.blocks:
            if b.kind == "table":
                kept.append(b)
                continue
            if b.page is not None and _key(b.text) in repeated:
                removed.append((b, "se repite en muchas páginas"))
                continue
            if BARE_PAGE.match(b.text):
                removed.append((b, "número de página"))
                continue
            text = PAGE_OF.sub("", b.text).strip()
            if not text:
                removed.append((b, "solo «Página X de Y»"))
                continue
            kept.append(b.with_(text=text) if text != b.text else b)
        return doc.with_blocks(kept, **dropped(doc, self.name, removed))
