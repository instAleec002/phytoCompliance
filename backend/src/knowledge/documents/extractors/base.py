"""What every extractor offers: the document as blocks (``structured``) and as Markdown (``markdown``).

An engine implements what it does natively and inherits the other from it: an engine with only a Markdown export gets
``structured`` by parsing that Markdown; one with only a structured output gets ``markdown`` by rendering it. ``native``
says which is native, so a route can prefer the native one and a report can say what was converted."""
from __future__ import annotations

from pathlib import Path

from ..markdown import parse_markdown, render_markdown
from ..model import MarkdownDocument, NormalizedDocument


class UnsupportedFormat(ValueError):
    pass


class Extractor:
    name: str = ""
    formats: frozenset[str] = frozenset()
    native: frozenset[str] = frozenset()       # "structured" and/or "markdown"

    def __init__(self, **options):
        self.options = options

    # Subclasses override at least one of the two -------------------------------------------------------------------

    def structured(self, path: Path, doc_id: str) -> NormalizedDocument:
        if "markdown" not in self.native:
            raise NotImplementedError(f"{self.name} no implementa ninguna salida")
        md = self.markdown(path, doc_id)
        return NormalizedDocument(doc_id=doc_id, title=md.title, source_format=md.source_format,
                                  blocks=tuple(parse_markdown(md)), pages=len(md.pages) if md.paged else None,
                                  meta={**md.meta, "structured_from": "markdown"})

    def markdown(self, path: Path, doc_id: str) -> MarkdownDocument:
        if "structured" not in self.native:
            raise NotImplementedError(f"{self.name} no implementa ninguna salida")
        doc = self.structured(path, doc_id)
        return MarkdownDocument(doc_id=doc_id, title=doc.title, source_format=doc.source_format,
                                pages=(render_markdown(doc),), paged=False,
                                meta={**doc.meta, "markdown_from": "structured"})

    # Helpers --------------------------------------------------------------------------------------------------------

    def check(self, path: Path) -> str:
        fmt = path.suffix.lower().lstrip(".")
        if fmt not in self.formats:
            raise UnsupportedFormat(f"{self.name} no lee .{fmt} (lee: {', '.join(sorted(self.formats))})")
        return fmt
