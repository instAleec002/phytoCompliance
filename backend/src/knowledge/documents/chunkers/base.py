"""What chunkers share: how a block reads inside a chunk, sentence splitting, page sets and chunk construction.

A chunker receives the document after its steps and returns ``Chunk`` objects without a header; the pipeline adds the
contextual header afterwards, so every chunker gets it the same way."""
from __future__ import annotations

import hashlib
import re
import warnings
from functools import lru_cache

from ..markdown.render import table_markdown
from ..model import Block, Chunk, NormalizedDocument
from ..steps.base import pages_of
from ..tokens import TokenCounter


def block_text(b: Block) -> str:
    """A block as it reads inside a chunk: list items keep their marker and indentation, tables are pipe tables
    (readable by both the encoder and the generator), captions stay plain."""
    if b.kind == "list_item":
        return "  " * max((b.level or 1) - 1, 0) + "- " + b.text
    if b.kind == "table":
        return table_markdown(b.cells) if b.cells else b.text
    return b.text


@lru_cache(maxsize=4)
def _segmenter(language: str):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        import pysbd
    return pysbd.Segmenter(language=language, clean=False)


def sentences(text: str, language: str = "es") -> list[str]:
    """Sentences by pySBD (Spanish rules: abbreviations such as «Dr.», «p.», decimals with comma). Splitting at
    sentence boundaries left no word cut in half on the edge cases of ragVersions-Scale."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        parts = _segmenter(language).segment(text)
    return [p.strip() for p in parts if p.strip()]


def split_long(text: str, budget: int, tokens: TokenCounter, language: str = "es") -> list[str]:
    """Pieces of at most ``budget`` tokens, cut between sentences; a single sentence longer than the budget is cut
    between words (the only case where a sentence is broken)."""
    pieces, current = [], ""
    for s in sentences(text, language):
        if tokens.count(s) > budget:
            if current:
                pieces.append(current)
                current = ""
            words, buf = s.split(), ""
            for w in words:
                cand = f"{buf} {w}".strip()
                if buf and tokens.count(cand) > budget:
                    pieces.append(buf)
                    buf = w
                else:
                    buf = cand
            if buf:
                pieces.append(buf)
            continue
        cand = f"{current} {s}".strip()
        if current and tokens.count(cand) > budget:
            pieces.append(current)
            current = s
        else:
            current = cand
    if current:
        pieces.append(current)
    return pieces


def chunk_id(doc_id: str, n: int, text: str) -> str:
    """Stable id: document, position and a short content hash (a changed text gives a new id)."""
    return f"{doc_id}:{n:04d}:{hashlib.sha256(text.encode('utf-8')).hexdigest()[:8]}"


class Chunker:
    name: str = ""

    def __init__(self, tokens: TokenCounter, language: str = "es", **options):
        self.tokens = tokens
        self.language = language
        self.options = options

    def make(self, doc: NormalizedDocument, n: int, texts: list[str], blocks: list[Block], **meta) -> Chunk:
        text = "\n\n".join(t for t in texts if t)
        pages = tuple(sorted({p for b in blocks for p in pages_of(b)}))
        section = blocks[0].section if blocks else ()
        return Chunk(chunk_id=chunk_id(doc.doc_id, n, text), doc_id=doc.doc_id, text=text, header="", pages=pages,
                     section=section, kinds=tuple(dict.fromkeys(b.kind for b in blocks)), tokens=self.tokens.count(text),
                     meta={"chunker": self.name, **meta})

    def __call__(self, doc: NormalizedDocument) -> list[Chunk]:  # pragma: no cover - interface
        raise NotImplementedError


def content_blocks(doc: NormalizedDocument) -> list[Block]:
    """Blocks that carry content: headings are structure (they live in the section path and the header), figures
    without text carry nothing."""
    return [b for b in doc.blocks if b.kind != "heading" and (b.text or b.cells) and not (b.kind == "figure" and not b.text)]


def same_section(a: Block, b: Block) -> bool:
    return a.section == b.section


SPACE = re.compile(r"\s+")
