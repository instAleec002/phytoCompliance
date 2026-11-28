"""Docling, for the extractor benchmark only (decision of 06/11/2026: OpenDataLoader is the PDF engine; Docling is not
a default anywhere). It reads PDF, DOCX and XLSX into its own document model; both outputs are native. Installed as
the optional extra ``docling`` (``uv sync --extra docling``); without it, choosing this extractor fails with that hint.

Options: ``ocr`` (default False), ``table_structure`` (default True)."""
from __future__ import annotations

from pathlib import Path

from ..model import Block, Cell, MarkdownDocument, NormalizedDocument
from ..registry import EXTRACTORS, register
from .base import Extractor

SKIP = {"page_header", "page_footer", "picture", "chart", "formula", "marker", "empty_value"}


@register(EXTRACTORS, "docling")
class DoclingExtractor(Extractor):
    name = "docling"
    formats = frozenset({"pdf", "docx", "xlsx"})
    native = frozenset({"structured", "markdown"})

    def __init__(self, **options):
        super().__init__(**options)
        self._cache: dict[tuple, object] = {}

    def _document(self, path: Path):
        fmt = self.check(path)
        st = path.stat()
        key = (str(path.resolve()), st.st_size, st.st_mtime_ns)
        if key not in self._cache:
            try:
                from docling.datamodel.base_models import InputFormat
                from docling.datamodel.pipeline_options import PdfPipelineOptions
                from docling.document_converter import DocumentConverter, PdfFormatOption
            except ImportError as e:  # pragma: no cover - depends on the optional extra
                raise RuntimeError("Docling no está instalado: uv sync --extra docling") from e
            opts = PdfPipelineOptions(do_ocr=bool(self.options.get("ocr", False)),
                                      do_table_structure=bool(self.options.get("table_structure", True)))
            converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
            self._cache = {key: (converter.convert(str(path)).document, fmt)}
        return self._cache[key]

    def structured(self, path: Path, doc_id: str) -> NormalizedDocument:
        doc, fmt = self._document(path)
        paged = fmt == "pdf"
        blocks: list[Block] = []
        for item, depth in doc.iterate_items():
            label = getattr(item, "label", None)
            label = getattr(label, "value", label)
            if label in SKIP:
                continue
            prov = getattr(item, "prov", None) or []
            page = prov[0].page_no if (paged and prov) else None
            if label == "table":
                cells = tuple(Cell(text=(c.text or "").strip(), row=c.start_row_offset_idx + 1, col=c.start_col_offset_idx + 1,
                                   row_span=c.row_span, col_span=c.col_span, header=bool(c.column_header))
                              for c in item.data.table_cells)
                if cells:
                    rows = sorted({c.row for c in cells})
                    text = "\n".join(" | ".join(c.text for c in cells if c.row == r) for r in rows)
                    blocks.append(Block("table", text, page, cells=cells))
                continue
            text = (getattr(item, "text", "") or "").strip()
            if not text:
                continue
            if label == "title":
                blocks.append(Block("heading", text, page, 1, meta={"title": True}))
            elif label == "section_header":
                blocks.append(Block("heading", text, page, (getattr(item, "level", 1) or 1) + 1))
            elif label == "list_item":
                blocks.append(Block("list_item", text, page, max(depth - 1, 1)))
            elif label == "caption":
                blocks.append(Block("caption", text, page))
            else:
                blocks.append(Block("paragraph", text, page, meta={"engine_label": label} if label != "text" else {}))
        title = next((b.text for b in blocks if b.meta.get("title")), path.stem)
        return NormalizedDocument(doc_id=doc_id, title=title, source_format=fmt, blocks=tuple(blocks),
                                  pages=doc.num_pages() if paged else None,
                                  meta={"engine": self.name, "options": dict(self.options)})

    def markdown(self, path: Path, doc_id: str) -> MarkdownDocument:
        doc, fmt = self._document(path)
        if fmt == "pdf":
            pages = tuple(doc.export_to_markdown(page_no=k) for k in range(1, doc.num_pages() + 1))
        else:
            pages = (doc.export_to_markdown(),)
        return MarkdownDocument(doc_id=doc_id, title=path.stem, source_format=fmt, pages=pages, paged=fmt == "pdf",
                                meta={"engine": self.name, "options": dict(self.options)})
