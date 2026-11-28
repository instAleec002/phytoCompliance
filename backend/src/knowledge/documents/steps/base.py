"""Steps: engine-independent fixes on a ``NormalizedDocument``. Each step is a registered class with a ``name`` and a
``__call__(doc) -> doc``; the configuration lists which run and in which order. A step that removes content records
what and why in ``doc.meta['dropped']``, so a report can always say what did not reach the index (idea taken from the
skipped-content log of ragVersions-Scale)."""
from __future__ import annotations

from ..model import Block, NormalizedDocument


class Step:
    name: str = ""

    def __init__(self, **options):
        self.options = options

    def __call__(self, doc: NormalizedDocument) -> NormalizedDocument:  # pragma: no cover - interface
        raise NotImplementedError


def dropped(doc: NormalizedDocument, step: str, removed: list[tuple[Block, str]]) -> dict:
    """``meta`` update that appends removed blocks (kind, page, first characters and the reason) to the log."""
    log = list(doc.meta.get("dropped", []))
    log += [{"step": step, "kind": b.kind, "page": b.page, "text": b.text[:120], "reason": why} for b, why in removed]
    return {"dropped": log}


def pages_of(block: Block) -> tuple[int, ...]:
    """Pages a block spans: a table merged across pages keeps them all in ``meta['pages']``."""
    if block.meta.get("pages"):
        return tuple(block.meta["pages"])
    return (block.page,) if block.page is not None else ()
