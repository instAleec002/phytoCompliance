"""Word (.docx) with python-docx. Structure is exact: heading styles give the levels, tables are real tables (merged
cells become spans), numbered and bulleted paragraphs become list items with their indentation level. There are no
pages, so blocks carry ``page=None`` and are cited by section.

Legacy ``.doc`` is not read: convert it to DOCX first (Word or LibreOffice)."""
from __future__ import annotations

import re
from pathlib import Path

from ..model import Block, Cell, NormalizedDocument
from ..registry import EXTRACTORS, register
from .base import Extractor

HEADING_STYLE = re.compile(r"^(?:heading|t[ií]tulo)\s*(\d)$", re.IGNORECASE)
TITLE_STYLE = re.compile(r"^(?:title|t[ií]tulo)$", re.IGNORECASE)
CAPTION_STYLE = re.compile(r"^(?:caption|descripci[oó]n|epígrafe|leyenda)$", re.IGNORECASE)
LIST_STYLE = re.compile(r"list|lista|vi[ñn]eta", re.IGNORECASE)
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _list_level(paragraph) -> int | None:
    ppr = paragraph._p.pPr
    num = ppr.numPr if ppr is not None else None
    if num is not None and num.numId is not None and num.numId.val != 0:
        return (num.ilvl.val if num.ilvl is not None else 0) + 1
    if LIST_STYLE.search(paragraph.style.name or ""):
        return 1
    return None


def _table(table) -> tuple[Cell, ...]:
    """Cells with spans. python-docx returns the same underlying cell for every grid position a merge covers, so a
    span is the extent of the positions that share one cell element."""
    seen: dict[int, list[int]] = {}
    texts: dict[int, str] = {}
    header_rows = {i for i, row in enumerate(table.rows) if row._tr.find(f"{W}trPr/{W}tblHeader") is not None}
    for r, row in enumerate(table.rows):
        for c, cell in enumerate(row.cells):
            key = id(cell._tc)
            if key not in seen:
                seen[key] = [r, c, r, c]
                texts[key] = " ".join(p.text.strip() for p in cell.paragraphs if p.text.strip())
            else:
                box = seen[key]
                box[2], box[3] = max(box[2], r), max(box[3], c)
    return tuple(Cell(text=texts[k], row=b[0] + 1, col=b[1] + 1, row_span=b[2] - b[0] + 1, col_span=b[3] - b[1] + 1,
                      header=b[0] in header_rows) for k, b in seen.items())


@register(EXTRACTORS, "docx")
class DocxExtractor(Extractor):
    name = "docx"
    formats = frozenset({"docx"})
    native = frozenset({"structured"})

    def structured(self, path: Path, doc_id: str) -> NormalizedDocument:
        self.check(path)
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        d = Document(str(path))
        title = (d.core_properties.title or "").strip()
        blocks: list[Block] = []
        for el in d.element.body.iterchildren():
            if el.tag == f"{W}p":
                p = Paragraph(el, d)
                text = p.text.strip()
                if not text:
                    continue
                style = p.style.name or ""
                if m := HEADING_STYLE.match(style):
                    blocks.append(Block("heading", text, None, int(m.group(1))))
                elif TITLE_STYLE.match(style):
                    title = title or text
                    blocks.append(Block("heading", text, None, 1, meta={"title": True}))
                elif CAPTION_STYLE.match(style):
                    blocks.append(Block("caption", text, None))
                elif (level := _list_level(p)) is not None:
                    blocks.append(Block("list_item", text, None, level))
                else:
                    bold = all(r.bold for r in p.runs if r.text.strip()) and any(r.text.strip() for r in p.runs)
                    blocks.append(Block("paragraph", text, None, meta={"bold": True} if bold else {}))
            elif el.tag == f"{W}tbl":
                cells = _table(Table(el, d))
                if any(c.text for c in cells):
                    rows = sorted({c.row for c in cells})
                    text = "\n".join(" | ".join(c.text for c in cells if c.row == r) for r in rows)
                    blocks.append(Block("table", text, None, cells=cells))
        return NormalizedDocument(doc_id=doc_id, title=title or path.stem, source_format="docx", blocks=tuple(blocks),
                                  pages=None, meta={"engine": self.name})
