"""Tables: layout grids that are not data, and tables that continue on the next page.

- A table whose cells are mostly empty (``max_empty``, default 0.8) or that has one column is a layout grid (a heading
  or a definition list drawn with a table): its rows become paragraphs. Threshold from ragVersions-Scale
  (``_is_fake_table``).
- Two tables with only furniture between them, on the same or the next page, with the same number of columns and the
  same header row (or an engine link saying one continues the other) are one table: rows are appended and the merged
  block keeps every page in ``meta['pages']`` (``_tables_are_continuation`` in ragVersions-Scale)."""
from __future__ import annotations

from ..model import Block, Cell, NormalizedDocument
from ..registry import STEPS, register
from .base import Step, pages_of


def _columns(b: Block) -> int:
    return max((c.col + c.col_span - 1 for c in b.cells), default=0)


def _header(b: Block) -> tuple[str, ...]:
    return tuple(c.text.strip().lower() for c in sorted(b.cells, key=lambda c: c.col) if c.row == 1)


def _rows_text(cells) -> str:
    rows = sorted({c.row for c in cells})
    return "\n".join(" | ".join(c.text for c in sorted(cells, key=lambda c: c.col) if c.row == r) for r in rows)


@register(STEPS, "tables")
class TablesStep(Step):
    name = "tables"

    def _is_layout(self, b: Block) -> bool:
        if not b.cells:
            return True
        empty = sum(1 for c in b.cells if not c.text.strip()) / len(b.cells)
        return empty > float(self.options.get("max_empty", 0.8)) or _columns(b) <= 1

    def _continues(self, a: Block, b: Block) -> bool:
        if a.meta.get("next_table_id") and a.meta.get("next_table_id") == b.meta.get("table_id"):
            return True
        pa, pb = pages_of(a), pages_of(b)
        if not pa or not pb or pb[0] - pa[-1] not in (0, 1) or _columns(a) != _columns(b):
            return False
        hb = _header(b)
        return hb == _header(a) or not any(c.header for c in b.cells)

    def _merge(self, a: Block, b: Block) -> Block:
        offset = max(c.row for c in a.cells)
        skip_header = _header(b) == _header(a) and any(c.header for c in b.cells)
        extra = [Cell(**{**c.__dict__, "row": c.row + offset - (1 if skip_header else 0), "header": False})
                 for c in b.cells if not (skip_header and c.row == 1)]
        cells = a.cells + tuple(extra)
        pages = tuple(dict.fromkeys(pages_of(a) + pages_of(b)))
        return a.with_(cells=cells, text=_rows_text(cells), meta={**a.meta, "pages": list(pages), "merged": True})

    def __call__(self, doc: NormalizedDocument) -> NormalizedDocument:
        out: list[Block] = []
        for b in doc.blocks:
            if b.kind == "table" and self._is_layout(b):
                for r in sorted({c.row for c in b.cells}):
                    text = " ".join(c.text for c in sorted(b.cells, key=lambda c: c.col) if c.row == r and c.text.strip())
                    if text:
                        out.append(Block("paragraph", text, b.page, meta={"from_layout_table": True}))
                continue
            if b.kind == "table" and out and out[-1].kind == "table" and self._continues(out[-1], b):
                out[-1] = self._merge(out[-1], b)
                continue
            out.append(b)
        return doc.with_blocks(out)
