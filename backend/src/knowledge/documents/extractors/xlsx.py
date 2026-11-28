"""Excel (.xlsx) with openpyxl: each sheet with content becomes a heading (the sheet name) followed by one table.
Merged ranges become spans; trailing empty rows and columns are trimmed. Formulas are read as their last computed
value. Programs to validate are not read here: they go to the program validator, which expects its own columns."""
from __future__ import annotations

from pathlib import Path

from ..model import Block, Cell, NormalizedDocument
from ..registry import EXTRACTORS, register
from .base import Extractor


def _value(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


@register(EXTRACTORS, "xlsx")
class XlsxExtractor(Extractor):
    name = "xlsx"
    formats = frozenset({"xlsx"})
    native = frozenset({"structured"})

    def structured(self, path: Path, doc_id: str) -> NormalizedDocument:
        self.check(path)
        from openpyxl import load_workbook

        wb = load_workbook(str(path), data_only=True, read_only=False)
        blocks: list[Block] = []
        for ws in wb.worksheets:
            grid = [[_value(v) for v in row] for row in ws.iter_rows(values_only=True)]
            while grid and not any(grid[-1]):
                grid.pop()
            if not grid:
                continue
            width = max((max((i + 1 for i, v in enumerate(r) if v), default=0) for r in grid), default=0)
            if width == 0:
                continue
            spans = {(m.min_row, m.min_col): (m.max_row - m.min_row + 1, m.max_col - m.min_col + 1)
                     for m in ws.merged_cells.ranges}
            covered = {(r, c) for (r0, c0), (rs, cs) in spans.items() for r in range(r0, r0 + rs) for c in range(c0, c0 + cs)
                       if (r, c) != (r0, c0)}
            cells = []
            for r, row in enumerate(grid, start=1):
                for c in range(1, width + 1):
                    if (r, c) in covered:
                        continue
                    rs, cs = spans.get((r, c), (1, 1))
                    cells.append(Cell(text=row[c - 1] if c - 1 < len(row) else "", row=r, col=c, row_span=rs,
                                      col_span=cs, header=r == 1))
            text = "\n".join(" | ".join(c.text for c in cells if c.row == r) for r in range(1, len(grid) + 1))
            blocks.append(Block("heading", ws.title, None, 1, meta={"sheet": True}))
            blocks.append(Block("table", text, None, cells=tuple(cells), meta={"sheet": ws.title}))
        title = (wb.properties.title or "").strip() or path.stem
        return NormalizedDocument(doc_id=doc_id, title=title, source_format="xlsx", blocks=tuple(blocks), pages=None,
                                  meta={"engine": self.name})
