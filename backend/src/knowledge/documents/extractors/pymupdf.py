"""PyMuPDF4LLM: fast, Markdown-native, one Markdown string per page. A baseline for the extractor benchmark; its blocks
come from parsing that Markdown.

Options: ``ocr`` (default False: OCR is not a priority and PyMuPDF4LLM would otherwise run it on image-only pages),
``ocr_language`` (default ``spa``), ``header`` and ``footer`` (default False: page furniture is not content)."""
from __future__ import annotations

from pathlib import Path

from ..model import MarkdownDocument
from ..registry import EXTRACTORS, register
from .base import Extractor


@register(EXTRACTORS, "pymupdf")
class PyMuPDFExtractor(Extractor):
    name = "pymupdf"
    formats = frozenset({"pdf"})
    native = frozenset({"markdown"})

    def markdown(self, path: Path, doc_id: str) -> MarkdownDocument:
        self.check(path)
        import pymupdf4llm  # imported here: it loads the layout model

        o = self.options
        pages = pymupdf4llm.to_markdown(str(path), page_chunks=True, show_progress=False,
                                        use_ocr=bool(o.get("ocr", False)), ocr_language=o.get("ocr_language", "spa"),
                                        header=bool(o.get("header", False)), footer=bool(o.get("footer", False)))
        meta = pages[0]["metadata"] if pages else {}
        return MarkdownDocument(doc_id=doc_id, title=(meta.get("title") or "").strip() or path.stem, source_format="pdf",
                                pages=tuple(p["text"] for p in pages), paged=True,
                                meta={"engine": self.name, "options": dict(o)})
