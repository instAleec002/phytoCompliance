"""Structural chunking (default): a chunk never crosses a section boundary, a table is never split, and long text is
cut between sentences.

Within a section, blocks are packed in reading order up to ``max_tokens``. A table is its own chunk, with an adjacent
caption attached; a table larger than the budget stays whole (splitting rows would separate values from their
headers). A paragraph or list item larger than the budget is split by sentences. A last piece under ``min_tokens``
joins the previous chunk of the same section when the result stays within ``max_tokens * 1.25``.

Options: ``max_tokens`` (default 480), ``min_tokens`` (default 80)."""
from __future__ import annotations

import re
from dataclasses import replace

from ..markdown.render import table_markdown
from ..model import Block, Chunk, NormalizedDocument
from ..registry import CHUNKERS, register
from .base import Chunker, block_text, content_blocks, split_long

# V4: sections that summarize or frame the document instead of carrying technical content
GENERIC = re.compile(r"^\W*(\d+(\.\d+)*\.?\s*)?(resumen|abstract|summary|introducci[oó]n|conclusi[oó]n(es)?|recomendaci[oó]n(es)?|"
                     r"objetivos?( general(es)?| espec[ií]ficos?)?|agradecimientos?|dedicatoria|presentaci[oó]n|pr[oó]logo|"
                     r"[ií]ndice|contenido|bibliograf[ií]a|referencias( bibliogr[aá]ficas)?|literatura citada|glosario)\b", re.IGNORECASE)


def is_generic(section: tuple[str, ...]) -> bool:
    return any(GENERIC.match(s or "") for s in section)


def table_groups(b: Block, budget: int, tokens) -> list[str]:
    """V6: a table as groups of rows that fit the budget, each starting with the header rows (marked as header, or
    the first row). A single row longer than the budget stays alone."""
    header_rows = sorted({c.row for c in b.cells if c.header}) or [min(c.row for c in b.cells)]
    head = [c for c in b.cells if c.row in header_rows]
    body_rows = sorted({c.row for c in b.cells} - set(header_rows))
    by_row = {r: [c for c in b.cells if c.row == r] for r in body_rows}

    def render(rows: list[int]) -> str:
        new = {r: i for i, r in enumerate(header_rows + rows, start=1)}
        return table_markdown(tuple(replace(c, row=new[c.row], row_span=1) for c in head + [x for r in rows for x in by_row[r]]))

    groups, current = [], []
    for r in body_rows:
        if current and tokens.count(render(current + [r])) > budget:
            groups.append(render(current))
            current = []
        current.append(r)
    if current:
        groups.append(render(current))
    return groups or [table_markdown(b.cells)]


def table_sentences(text: str) -> str:
    """V6b: a pipe table (with any caption around it) in a form the encoder reads well; the user still sees the table.

    PDF extraction often breaks one logical row into several physical rows when a cell wraps («Trichoderma» /
    «viride», one crop per line) and splits a long header («INGREDIENTE» / «ACTIVO»). So:
    - a first body row with a single filled cell continues the header (in tables of three or more columns);
    - a wrapped table (30 % or more of its body rows have an empty first cell) is written by column,
      «Columna: valor valor ….», which joins the pieces of each cell back;
    - a clean table is written as one sentence per row, «Columna: valor; Columna: valor.», empty cells left out.
    Lines that are not part of the table (the caption) are kept as they are."""
    lines = [ln.strip() for ln in text.split("\n")]
    out: list[str] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("|") and i + 1 < len(lines) and lines[i + 1] and set(lines[i + 1]) <= set("|-: "):
            head = [c.strip() for c in ln.strip("|").split("|")]
            body, i = [], i + 2
            while i < len(lines) and lines[i].startswith("|"):
                body.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            out.extend(_table_lines(head, body))
            continue
        if ln:
            out.append(ln)
        i += 1
    return "\n".join(out)


def _table_lines(head: list[str], body: list[list[str]]) -> list[str]:
    n = len(head)
    body = [(r + [""] * n)[:n] for r in body]
    while body and n >= 3 and sum(1 for c in body[0] if c) == 1:          # header continued on the next physical row
        head = [f"{h} {c}".strip() for h, c in zip(head, body.pop(0))]
    if not body:
        return []
    wrapped = sum(1 for r in body if not r[0]) / len(body) >= 0.3
    if wrapped:
        cols = [" ".join(r[k] for r in body if r[k]) for k in range(n)]
        return ["; ".join(f"{h}: {v}" if h else v for h, v in zip(head, cols) if v) + "."]
    lines = []
    for r in body:
        pairs = [f"{h}: {v}" if h else v for h, v in zip(head, r) if v]
        if pairs:
            lines.append("; ".join(pairs) + ".")
    return lines

@register(CHUNKERS, "structural")
class StructuralChunker(Chunker):
    name = "structural"

    def units(self, doc: NormalizedDocument) -> list[tuple[list[str], list[Block], str]]:
        """(texts, source blocks, unit kind) before chunk ids are assigned; ``parent_child`` reuses it."""
        max_t = int(self.options.get("max_tokens", 480))
        min_t = int(self.options.get("min_tokens", 80))
        blocks = content_blocks(doc)
        if self.options.get("generic_sections") == "drop":
            blocks = [b for b in blocks if not is_generic(b.section)]
        units: list[tuple[list[str], list[Block], str]] = []
        texts: list[str] = []
        src: list[Block] = []

        def flush():
            if texts:
                units.append((list(texts), list(src), "text"))
                texts.clear()
                src.clear()

        i = 0
        while i < len(blocks):
            b = blocks[i]
            if src and b.section != src[0].section:
                flush()
            if b.kind == "table":
                flush()
                parts, used = [block_text(b)], [b]
                if units and units[-1][2] == "text" and units[-1][1][-1].kind == "caption" \
                        and units[-1][1][-1].section == b.section:
                    cap_texts, cap_src, _ = units.pop()
                    if len(cap_src) > 1:                       # keep the text before the caption as its own unit
                        units.append((cap_texts[:-1], cap_src[:-1], "text"))
                    parts, used = [cap_texts[-1], *parts], [cap_src[-1], *used]
                elif i + 1 < len(blocks) and blocks[i + 1].kind == "caption" and blocks[i + 1].section == b.section:
                    parts.append(blocks[i + 1].text)
                    used.append(blocks[i + 1])
                    i += 1
                if self.options.get("table_rows") and b.cells and self.tokens.count("\n\n".join(parts)) > max_t:
                    lead = [p for p, u in zip(parts, used) if u is not b]          # the caption, repeated with each group
                    budget = max(max_t - self.tokens.count("\n\n".join(lead)), max_t // 2)
                    for g in table_groups(b, budget, self.tokens):
                        units.append(([*lead, g], used, "table"))
                else:
                    units.append((parts, used, "table"))
                i += 1
                continue
            t = block_text(b)
            n = self.tokens.count(t)
            if n > max_t:
                flush()
                for piece in split_long(t, max_t, self.tokens, self.language):
                    units.append(([piece], [b], "text"))
                i += 1
                continue
            if texts and self.tokens.count("\n\n".join([*texts, t])) > max_t:
                flush()
            texts.append(t)
            src.append(b)
            i += 1
        flush()

        merged: list[tuple[list[str], list[Block], str]] = []
        for u in units:
            prev = merged[-1] if merged else None
            if (prev and u[2] == "text" and prev[2] == "text" and prev[1][0].section == u[1][0].section
                    and self.tokens.count("\n\n".join(u[0])) < min_t
                    and self.tokens.count("\n\n".join(prev[0] + u[0])) <= max_t * 1.25):
                merged[-1] = (prev[0] + u[0], prev[1] + u[1], "text")
            else:
                merged.append(u)

        mst = self.options.get("merge_section_tokens")
        if not mst:
            return merged
        # V2: a small text unit joins the next text unit of the same parent section while the result fits the budget
        out: list[tuple[list[str], list[Block], str]] = []
        i = 0
        while i < len(merged):
            u = merged[i]
            while (u[2] == "text" and i + 1 < len(merged) and merged[i + 1][2] == "text"
                   and self.tokens.count("\n\n".join(u[0])) < int(mst)
                   and u[1][0].section[:-1] == merged[i + 1][1][0].section[:-1]
                   and self.tokens.count("\n\n".join(u[0] + merged[i + 1][0])) <= max_t):
                u = (u[0] + merged[i + 1][0], u[1] + merged[i + 1][1], "text")
                i += 1
            out.append(u)
            i += 1
        return out

    def __call__(self, doc: NormalizedDocument) -> list[Chunk]:
        chunks = [self.make(doc, n, texts, blocks, unit=kind) for n, (texts, blocks, kind) in enumerate(self.units(doc))]
        if self.options.get("table_text") == "filas":
            chunks = [replace(c, vector_text=table_sentences(c.text)) if c.meta.get("unit") == "table" else c for c in chunks]
        return chunks
