"""Blocks to Markdown. Used by the Markdown route for formats without a native Markdown export (DOCX, XLSX), to show a
document to a person, and to give a table to the generator in a form it reads well."""
from __future__ import annotations

from ..model import Block, Cell, NormalizedDocument

PAGE_ANCHOR = "<!-- page {n} -->"


def _escape(text: str) -> str:
    return text.replace("|", r"\|").replace("\n", " ").strip()


def table_markdown(cells: tuple[Cell, ...]) -> str:
    """A pipe table. Spanned cells repeat nothing: the text sits in the first cell of the span, as the source shows it.
    The first row is the header row (Markdown needs one); if the source marks none, the first row is used."""
    if not cells:
        return ""
    rows = max(c.row for c in cells)
    cols = max(c.col + c.col_span - 1 for c in cells)
    grid = [["" for _ in range(cols)] for _ in range(rows)]
    for c in cells:
        grid[c.row - 1][c.col - 1] = _escape(c.text)
    lines = ["| " + " | ".join(grid[0]) + " |", "|" + "---|" * cols]
    lines += ["| " + " | ".join(r) + " |" for r in grid[1:]]
    return "\n".join(lines)


def block_markdown(b: Block) -> str:
    if b.kind == "heading":
        return "#" * min(max(b.level or 1, 1), 6) + " " + b.text
    if b.kind == "list_item":
        return "  " * max((b.level or 1) - 1, 0) + "- " + b.text
    if b.kind == "table":
        return table_markdown(b.cells)
    if b.kind == "caption":
        return f"_{b.text}_"
    if b.kind == "figure":
        return f"![{_escape(b.text)}](figura)"
    return b.text


def render_markdown(doc: NormalizedDocument, anchors: bool = True) -> str:
    out: list[str] = []
    page = None
    for b in doc.blocks:
        if anchors and b.page is not None and b.page != page:
            out.append(PAGE_ANCHOR.format(n=b.page))
            page = b.page
        out.append(block_markdown(b))
    return "\n\n".join(out) + "\n"
