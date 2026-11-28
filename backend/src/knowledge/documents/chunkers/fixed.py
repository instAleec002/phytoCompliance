"""Fixed-size chunking: the baseline the ablation compares against. The whole document is read as one text and cut
every ``max_tokens`` with ``overlap_tokens`` of overlap, between words; sections and tables are ignored on purpose.
Each chunk records the pages and the section of the blocks it covers (the section of its first block).

Options: ``max_tokens`` (default 480), ``overlap_tokens`` (default 60)."""
from __future__ import annotations

from ..model import Block, Chunk, NormalizedDocument
from ..registry import CHUNKERS, register
from .base import Chunker, block_text, content_blocks


@register(CHUNKERS, "fixed")
class FixedChunker(Chunker):
    name = "fixed"

    def __call__(self, doc: NormalizedDocument) -> list[Chunk]:
        max_t = int(self.options.get("max_tokens", 480))
        overlap = int(self.options.get("overlap_tokens", 60))
        words: list[tuple[str, Block]] = [(w, b) for b in content_blocks(doc) for w in block_text(b).split()]
        chunks, start, n = [], 0, 0
        while start < len(words):
            end, text = start, ""
            while end < len(words):
                cand = f"{text} {words[end][0]}".strip()
                if text and self.tokens.count(cand) > max_t:
                    break
                text, end = cand, end + 1
            blocks = list(dict.fromkeys(b for _, b in words[start:end]))
            chunks.append(self.make(doc, n, [text], blocks, overlap_tokens=overlap))
            n += 1
            if end >= len(words):
                break
            back, kept = end, 0
            while back > start + 1 and kept < overlap:
                back -= 1
                kept = self.tokens.count(" ".join(w for w, _ in words[back:end]))
            start = back if back > start else end
        return chunks
