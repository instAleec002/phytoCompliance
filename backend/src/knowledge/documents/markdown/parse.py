"""Markdown back to blocks. Reads the subset that the engines and ``render`` emit: ATX headings, lists, pipe tables,
italic-only lines as captions, images as figures, and ``<!-- page N -->`` anchors. Inline emphasis is removed from the
text; a paragraph that was entirely bold is marked (``meta['bold']``) so the outline step may promote it to a
heading, since engines often lose heading styles."""
from __future__ import annotations

import re

from ..model import Block, Cell, MarkdownDocument

PAGE_RE = re.compile(r"^\s*<!--\s*page\s+(\d+)\s*-->\s*$", re.IGNORECASE)
COMMENT_RE = re.compile(r"^\s*<!--.*-->\s*$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
LIST_RE = re.compile(r"^(\s*)(?:[-*+]|\d{1,3}[.)])\s+(.*)$")
TABLE_RE = re.compile(r"^\s*\|.*\|\s*$")
SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
CAPTION_RE = re.compile(r"^\s*(?:_([^_].*?)_|\*([^*].*?)\*)\s*$")
IMAGE_RE = re.compile(r"^\s*!\[([^\]]*)\]\([^)]*\)\s*$")
BOLD_LINE_RE = re.compile(r"^\s*(?:\*\*|__)(.+?)(?:\*\*|__)\s*$")
EMPHASIS_RE = re.compile(r"(\*\*|__|(?<!\w)[*_](?=\S)|(?<=\S)[*_](?!\w))")


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", EMPHASIS_RE.sub("", text)).strip()


def _cells(line: str) -> list[str]:
    inner = line.strip().strip("|")
    parts = re.split(r"(?<!\\)\|", inner)
    return [p.replace(r"\|", "|").strip() for p in parts]


def _table(lines: list[str], page: int | None) -> Block:
    header_rows = 1 if len(lines) > 1 and SEPARATOR_RE.match(lines[1]) else 0
    rows = [ln for i, ln in enumerate(lines) if not (header_rows and i == 1)]
    cells = []
    for r, ln in enumerate(rows, start=1):
        for c, text in enumerate(_cells(ln), start=1):
            cells.append(Cell(text=_plain(text), row=r, col=c, header=bool(header_rows) and r == 1))
    text = "\n".join(" | ".join(c.text for c in cells if c.row == r) for r in range(1, len(rows) + 1))
    return Block(kind="table", text=text, page=page, cells=tuple(cells))


def _parse_text(md: str, page: int | None, blocks: list[Block]) -> int | None:
    lines = md.splitlines()
    para: list[str] = []
    i = 0

    def flush():
        if para:
            raw = " ".join(s.strip() for s in para)
            bold = BOLD_LINE_RE.match(raw) is not None
            text = _plain(raw)
            if text:
                blocks.append(Block(kind="paragraph", text=text, page=page, meta={"bold": True} if bold else {}))
            para.clear()

    while i < len(lines):
        line = lines[i]
        if m := PAGE_RE.match(line):
            flush()
            page = int(m.group(1))
        elif COMMENT_RE.match(line) or not line.strip():
            flush()
        elif m := HEADING_RE.match(line):
            flush()
            text = _plain(m.group(2))
            if text:
                blocks.append(Block(kind="heading", text=text, page=page, level=len(m.group(1))))
        elif TABLE_RE.match(line):
            flush()
            start = i
            while i + 1 < len(lines) and TABLE_RE.match(lines[i + 1]):
                i += 1
            blocks.append(_table(lines[start:i + 1], page))
        elif m := IMAGE_RE.match(line):
            flush()
            blocks.append(Block(kind="figure", text=_plain(m.group(1)), page=page))
        elif m := LIST_RE.match(line):
            flush()
            depth = len(m.group(1).replace("\t", "  ")) // 2 + 1
            text = _plain(m.group(2))
            if text:
                blocks.append(Block(kind="list_item", text=text, page=page, level=depth))
        elif (m := CAPTION_RE.match(line)) and not para:
            blocks.append(Block(kind="caption", text=_plain(m.group(1) or m.group(2)), page=page))
        else:
            para.append(line)
        i += 1
    flush()
    return page


def parse_markdown(md: MarkdownDocument | str, first_page: int | None = None) -> list[Block]:
    """Blocks from Markdown. With a ``MarkdownDocument`` whose items are pages, item *k* is page *k* unless an anchor
    inside says otherwise; a non-paged document (DOCX, XLSX) gives blocks with ``page=None``."""
    blocks: list[Block] = []
    if isinstance(md, str):
        _parse_text(md, first_page, blocks)
        return blocks
    for k, text in enumerate(md.pages, start=1):
        _parse_text(text, k if md.paged else None, blocks)
    return blocks
