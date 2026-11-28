"""Parent-child chunking ("small to big"): small children are embedded and searched, and the larger parent they belong
to is what the generator reads. Parents are the structural chunks; children are sentence windows of about
``child_tokens``. Every chunk has ``meta['role']``:

- ``child``: embedded, with ``meta['parent_id']``;
- ``parent``: not embedded, returned with its children;
- ``atomic``: a parent that would have a single child identical to itself (a short section, a table) is stored once
  and embedded itself. Keeping both halves duplicated content under two ids and once led to a cleanup that deleted the
  searchable half (``pair_collapses_to_parent`` in ragVersions-Scale).

Options: ``max_tokens`` and ``min_tokens`` for parents (as ``structural``), ``child_tokens`` (default 160)."""
from __future__ import annotations

from ..model import Chunk, NormalizedDocument
from ..registry import CHUNKERS, register
from .base import split_long
from .structural import StructuralChunker


@register(CHUNKERS, "parent_child")
class ParentChildChunker(StructuralChunker):
    name = "parent_child"

    def __call__(self, doc: NormalizedDocument) -> list[Chunk]:
        child_t = int(self.options.get("child_tokens", 160))
        out: list[Chunk] = []
        n = 0
        for texts, blocks, kind in self.units(doc):
            parent_text = "\n\n".join(texts)
            pieces = [parent_text] if kind == "table" else split_long(parent_text, child_t, self.tokens, self.language)
            if len(pieces) <= 1:
                out.append(self.make(doc, n, texts, blocks, unit=kind, role="atomic"))
                n += 1
                continue
            parent = self.make(doc, n, texts, blocks, unit=kind, role="parent")
            out.append(parent)
            n += 1
            for piece in pieces:
                out.append(self.make(doc, n, [piece], blocks, unit=kind, role="child", parent_id=parent.chunk_id))
                n += 1
        return out
