"""Section paths: each block gets the path of headings above it (the document title, level 0, is left out: it goes in
the contextual header). A heading's own path ends with itself. A heading with ``meta['scope']`` (an annex whose
numbering restarted) opens that scope as the root of the path. Runs last."""
from __future__ import annotations

from ..model import NormalizedDocument
from ..registry import STEPS, register
from .base import Step


@register(STEPS, "sections")
class SectionsStep(Step):
    name = "sections"

    def __call__(self, doc: NormalizedDocument) -> NormalizedDocument:
        stack: list[tuple[int, str]] = []
        out = []
        for b in doc.blocks:
            if b.kind == "heading" and (b.level or 0) > 0:
                if b.meta.get("scope"):
                    stack = [(0, b.meta["scope"])]
                level = b.level or 1
                stack = [(lv, t) for lv, t in stack if lv < level]
                stack.append((level, b.text))
                out.append(b.with_(section=tuple(t for _, t in stack)))
            else:
                out.append(b.with_(section=tuple(t for _, t in stack)))
        return doc.with_blocks(out)
