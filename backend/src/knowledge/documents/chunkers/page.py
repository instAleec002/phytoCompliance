"""Page chunking: one chunk per page, the unit some end-to-end benchmarks favour (reported for NVIDIA's 2025 test,
secondary source; to be checked in our own ablation). A page longer than ``max_tokens`` is split by sentences. A
document without pages (DOCX, XLSX) falls back to one chunk per top-level section.

Options: ``max_tokens`` (default 1200)."""
from __future__ import annotations

from itertools import groupby

from ..model import Chunk, NormalizedDocument
from ..registry import CHUNKERS, register
from .base import Chunker, block_text, content_blocks, split_long


@register(CHUNKERS, "page")
class PageChunker(Chunker):
    name = "page"

    def __call__(self, doc: NormalizedDocument) -> list[Chunk]:
        max_t = int(self.options.get("max_tokens", 1200))
        blocks = content_blocks(doc)
        paged = any(b.page is not None for b in blocks)
        key = (lambda b: b.page) if paged else (lambda b: b.section[:1])
        chunks, n = [], 0
        for _, group in groupby(blocks, key=key):
            group = list(group)
            text = "\n\n".join(block_text(b) for b in group)
            pieces = [text] if self.tokens.count(text) <= max_t else split_long(text, max_t, self.tokens, self.language)
            for piece in pieces:
                chunks.append(self.make(doc, n, [piece], group))
                n += 1
        return chunks
