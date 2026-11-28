"""Routes: how a file becomes blocks.

- ``markdown`` (default): the extractor's Markdown, parsed into blocks. Engines tend to be strongest at their Markdown
  export (reading order, list markers), and the Markdown is easy to inspect.
- ``structured``: the extractor's own typed output (headings with levels, tables with spans, lists with depth).
- ``mixed``: text from Markdown, tables from the structured output. Markdown flattens merged cells and multi-row
  headers; the structured table keeps them. Each structured table replaces the Markdown table it corresponds to (same
  page, closest row count); a structured table with no Markdown counterpart is placed after the Markdown block that
  precedes it in the structured output, or at the end of its page. For formats without pages (DOCX, XLSX) the
  structured output is already exact and ``mixed`` returns it.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from .extractors.base import Extractor
from .markdown import parse_markdown
from .model import Block, NormalizedDocument

ROUTES = ("markdown", "structured", "mixed")


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()[:80]


def via_markdown(extractor: Extractor, path: Path, doc_id: str) -> NormalizedDocument:
    md = extractor.markdown(path, doc_id)
    blocks = tuple(parse_markdown(md))
    # one Markdown string with page anchors (OpenDataLoader): the page count is the highest anchor
    anchored = max((b.page for b in blocks if b.page is not None), default=None)
    return NormalizedDocument(doc_id=doc_id, title=md.title, source_format=md.source_format, blocks=blocks,
                              pages=len(md.pages) if md.paged else anchored, meta={**md.meta, "route": "markdown"})


def via_structured(extractor: Extractor, path: Path, doc_id: str) -> NormalizedDocument:
    doc = extractor.structured(path, doc_id)
    return doc.with_blocks(doc.blocks, route="structured")


def merge_mixed(md_doc: NormalizedDocument, st_doc: NormalizedDocument) -> NormalizedDocument:
    if all(b.page is None for b in st_doc.blocks):
        return st_doc.with_blocks(st_doc.blocks, route="mixed")
    st_tables = defaultdict(list)
    previous_text: dict[int, str] = {}
    last = ""
    for b in st_doc.blocks:
        if b.kind == "table":
            st_tables[b.page].append(b)
            previous_text[id(b)] = last
        else:
            last = _norm(b.text)
    out: list[Block] = []
    used: set[int] = set()
    for b in md_doc.blocks:
        if b.kind == "table":
            candidates = [t for t in st_tables.get(b.page, []) if id(t) not in used]
            if candidates:
                rows = len({c.row for c in b.cells}) or 1
                best = min(candidates, key=lambda t: abs(len({c.row for c in t.cells}) - rows))
                used.add(id(best))
                out.append(best)
                continue
        out.append(b)
    for page, tables in st_tables.items():
        for t in tables:
            if id(t) in used:
                continue
            anchor = previous_text.get(id(t), "")
            pos = next((i + 1 for i in range(len(out) - 1, -1, -1)
                        if out[i].page == page and anchor and _norm(out[i].text).startswith(anchor[:40])), None)
            if pos is None:
                pos = next((i + 1 for i in range(len(out) - 1, -1, -1) if out[i].page == page), len(out))
            out.insert(pos, t)
    return md_doc.with_blocks(out, route="mixed", tables_from="structured")


def via_mixed(extractor: Extractor, path: Path, doc_id: str) -> NormalizedDocument:
    return merge_mixed(via_markdown(extractor, path, doc_id), via_structured(extractor, path, doc_id))


def read(route: str, extractor: Extractor, path: Path, doc_id: str) -> NormalizedDocument:
    if route == "markdown":
        return via_markdown(extractor, path, doc_id)
    if route == "structured":
        return via_structured(extractor, path, doc_id)
    if route == "mixed":
        return via_mixed(extractor, path, doc_id)
    raise ValueError(f"Ruta desconocida: {route!r}. Disponibles: {', '.join(ROUTES)}")
