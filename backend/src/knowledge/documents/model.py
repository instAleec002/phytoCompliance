"""The contract between stages: a document as typed blocks, and the chunks made from it.

Extractors produce a ``NormalizedDocument``; steps return a new one; chunkers turn it into ``Chunk`` objects. Every
object is frozen, so a stage can never change what an earlier stage produced, and the same input always gives the
same output.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal

BlockKind = Literal["heading", "paragraph", "list_item", "table", "caption", "figure"]


@dataclass(frozen=True)
class Cell:
    text: str
    row: int
    col: int
    row_span: int = 1
    col_span: int = 1
    header: bool = False


@dataclass(frozen=True)
class Block:
    """One unit of content in reading order.

    ``page`` is 1-based and ``None`` for formats without pages (DOCX). ``level`` is the heading level for headings and
    the nesting depth for list items. ``section`` is the path of headings above the block, filled by the ``sections``
    step; chunks and citations use it."""

    kind: BlockKind
    text: str
    page: int | None = None
    level: int | None = None
    cells: tuple[Cell, ...] = ()
    section: tuple[str, ...] = ()
    meta: dict = field(default_factory=dict, compare=False, hash=False)

    def with_(self, **changes) -> Block:
        return replace(self, **changes)


@dataclass(frozen=True)
class NormalizedDocument:
    """A document as blocks, plus where it came from and how it was read."""

    doc_id: str
    title: str
    source_format: str                 # pdf, docx, xlsx
    blocks: tuple[Block, ...]
    pages: int | None = None
    meta: dict = field(default_factory=dict, compare=False, hash=False)   # engine, route, steps applied

    def with_blocks(self, blocks, **meta) -> NormalizedDocument:
        return replace(self, blocks=tuple(blocks), meta={**self.meta, **meta})


@dataclass(frozen=True)
class MarkdownDocument:
    """What an engine's Markdown export gives: one Markdown string per page (one item when the format has no pages)."""

    doc_id: str
    title: str
    source_format: str
    pages: tuple[str, ...]
    paged: bool = True                 # False for DOCX and XLSX: the single item is not a page
    meta: dict = field(default_factory=dict, compare=False, hash=False)


@dataclass(frozen=True)
class Chunk:
    """A unit to index and to cite. ``text`` is the content; ``header`` is the contextual header (document title and
    section path) that is prepended for embedding and shown with the citation."""

    chunk_id: str
    doc_id: str
    text: str
    header: str
    pages: tuple[int, ...]
    section: tuple[str, ...]
    kinds: tuple[str, ...]
    tokens: int
    meta: dict = field(default_factory=dict, compare=False, hash=False)
    # what the encoder reads instead of `text` when set (tables written as sentences); `text` is still what the user
    # and the generator see
    vector_text: str = ""

    @property
    def embedding_text(self) -> str:
        body = self.vector_text or self.text
        return f"{self.header}\n\n{body}" if self.header else body
