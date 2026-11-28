"""OpenDataLoader PDF (Java engine with a Python wrapper; needs Java 11+). Both outputs are native: its JSON (typed
elements with page, heading level, lists and tables with spans) and its Markdown export, with page anchors requested
through ``markdown_page_separator``. One conversion produces both and is cached, so the ``mixed`` route reads the file
once.

Options (``extractor_options.opendataloader`` in ``config/documents.yaml``): ``table_method`` (default, cluster),
``reading_order`` (xycut, off), ``use_struct_tree``, ``hybrid``, ``hybrid_mode``, ``hybrid_url``, ``keep_line_breaks``
and ``threads`` pass through to ``convert``; ``fast_jvm`` and ``cds`` (both default True) speed up the JVM start.
Page headers and footers are left out by the engine (``include_header_footer=False``)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from ..model import Block, Cell, MarkdownDocument, NormalizedDocument
from ..registry import EXTRACTORS, register
from .base import Extractor

PASSTHROUGH = {"table_method", "reading_order", "use_struct_tree", "hybrid", "hybrid_mode", "hybrid_url",
               "keep_line_breaks", "threads"}


def _text(node: dict) -> str:
    """All text under a node (a table cell holds paragraphs, a list item may hold nested elements)."""
    parts = [node.get("content", "")] if node.get("content") else []
    for kid in node.get("kids") or []:
        parts.append(_text(kid))
    for item in node.get("list items") or []:
        parts.append(_text(item))
    return " ".join(p for p in parts if p).strip()


def _page(node: dict) -> int | None:
    p = node.get("page number")
    return int(p) if p not in (None, "") else None


@register(EXTRACTORS, "opendataloader")
class OpenDataLoaderExtractor(Extractor):
    name = "opendataloader"
    formats = frozenset({"pdf"})
    native = frozenset({"structured", "markdown"})

    def __init__(self, **options):
        super().__init__(**options)
        self._cache: dict[tuple, tuple[dict, str]] = {}

    @staticmethod
    def _key(path: Path) -> tuple:
        st = path.stat()
        return (str(path.resolve()), st.st_size, st.st_mtime_ns)

    def _jvm_options(self) -> str:
        """Startup flags for the engine's JVM, which is most of the time on short files (measured in ragVersions-Scale):
        C1-only compilation and a class-data-sharing archive, created on the first run and reused afterwards."""
        flags = []
        if self.options.get("fast_jvm", True):
            flags.append("-XX:TieredStopAtLevel=1")
        if self.options.get("cds", True):
            from shared.settings import REPO

            archive = REPO / "non_local" / "non_cache" / "odl.jsa"
            archive.parent.mkdir(parents=True, exist_ok=True)
            flags.append(f"-XX:SharedArchiveFile={archive}" if archive.exists() else f"-XX:ArchiveClassesAtExit={archive}")
        return " ".join(flags)

    def prepare(self, paths: list[Path]) -> None:
        """Converts several PDFs in one engine call (one JVM start for all; 1.75x faster for three files in
        ragVersions-Scale) and keeps the results for ``structured`` and ``markdown``."""
        todo = [p for p in paths if p.suffix.lower() == ".pdf" and self._key(p) not in self._cache]
        if not todo:
            return
        # the engine names each output after the file stem: two inputs with the same stem go in separate calls
        batches: list[list[Path]] = []
        for p in todo:
            target = next((b for b in batches if all(q.stem != p.stem for q in b)), None)
            if target is None:
                batches.append([p])
            else:
                target.append(p)
        if len(batches) > 1:
            for b in batches:
                self.prepare(b)
            return
        import os

        import opendataloader_pdf  # imported here: the engine starts a JVM

        params = {k: v for k, v in self.options.items() if k in PASSTHROUGH and v is not None}
        before = os.environ.get("JAVA_TOOL_OPTIONS")
        os.environ["JAVA_TOOL_OPTIONS"] = " ".join(x for x in (before, self._jvm_options()) if x)
        try:
            with tempfile.TemporaryDirectory(prefix="odl_") as out:
                opendataloader_pdf.convert(input_path=[str(p) for p in todo], output_dir=out, format="json,markdown",
                                           quiet=True, image_output="off", include_header_footer=False,
                                           markdown_page_separator="<!-- page %page-number% -->", **params)
                for p in todo:
                    js, md = Path(out) / f"{p.stem}.json", Path(out) / f"{p.stem}.md"
                    if not js.exists():
                        raise RuntimeError(f"OpenDataLoader no produjo salida para {p.name}")
                    self._cache[self._key(p)] = (json.loads(js.read_text(encoding="utf-8")),
                                                 md.read_text(encoding="utf-8") if md.exists() else "")
        finally:
            if before is None:
                os.environ.pop("JAVA_TOOL_OPTIONS", None)
            else:
                os.environ["JAVA_TOOL_OPTIONS"] = before

    def release(self, path: Path) -> None:
        self._cache.pop(self._key(path), None)

    def _convert(self, path: Path) -> tuple[dict, str]:
        self.check(path)
        if self._key(path) not in self._cache:
            self.prepare([path])
        return self._cache[self._key(path)]

    def _blocks(self, nodes, out: list[Block], depth: int = 0) -> None:
        for n in nodes or []:
            kind, page = n.get("type"), _page(n)
            if kind == "heading":
                level = int(n.get("heading level") or 1)
                meta = {"engine_level": n.get("level")}
                if str(n.get("level", "")).lower() in ("doctitle", "title"):
                    meta["title"] = True
                out.append(Block("heading", n.get("content", "").strip(), page, level, meta=meta))
            elif kind in ("paragraph", "text block"):
                text = n.get("content", "").strip() or _text(n)
                if text:
                    out.append(Block("paragraph", text, page))
            elif kind == "caption":
                out.append(Block("caption", n.get("content", "").strip(), page))
            elif kind == "list":
                for item in n.get("list items") or []:
                    text = (item.get("content") or "").strip()
                    if text:
                        out.append(Block("list_item", text, _page(item) or page, depth + 1))
                    self._blocks(item.get("kids"), out, depth + 1)
            elif kind == "table":
                cells = []
                for row in n.get("rows") or []:
                    for c in row.get("cells") or []:
                        cells.append(Cell(text=_text(c), row=int(c.get("row number", 1)), col=int(c.get("column number", 1)),
                                          row_span=int(c.get("row span", 1)), col_span=int(c.get("column span", 1)),
                                          header=str(c.get("is_header", "")).lower() == "true"))
                if cells:
                    rows = sorted({c.row for c in cells})
                    text = "\n".join(" | ".join(c.text for c in cells if c.row == r) for r in rows)
                    meta = {"table_id": n.get("id")}
                    if n.get("next table id"):
                        meta["next_table_id"] = n["next table id"]       # continuation link, used by the tables step
                    out.append(Block("table", text, page, cells=tuple(cells), meta=meta))
            elif kind == "image":
                continue                                   # no alt text in these documents: nothing to index
            else:
                if n.get("content"):
                    out.append(Block("paragraph", n["content"].strip(), page, meta={"engine_type": kind}))
                self._blocks(n.get("kids"), out, depth)

    def structured(self, path: Path, doc_id: str) -> NormalizedDocument:
        data, _ = self._convert(path)
        blocks: list[Block] = []
        self._blocks(data.get("kids"), blocks)
        pages = data.get("number of pages")
        return NormalizedDocument(doc_id=doc_id, title=(data.get("title") or "").strip() or path.stem, source_format="pdf",
                                  blocks=tuple(blocks), pages=int(pages) if pages else None,
                                  meta={"engine": self.name, "options": dict(self.options)})

    def markdown(self, path: Path, doc_id: str) -> MarkdownDocument:
        data, md = self._convert(path)
        return MarkdownDocument(doc_id=doc_id, title=(data.get("title") or "").strip() or path.stem, source_format="pdf",
                                pages=(md,), paged=False, meta={"engine": self.name, "options": dict(self.options)})
