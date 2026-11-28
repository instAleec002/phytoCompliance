"""The pipeline: a file in, a normalized document and its chunks out, exactly as the configuration says.

    pipeline = Pipeline(load_config(route="structured", chunker="fixed"))
    result = pipeline.process(Path("manual.pdf"), doc_id="inia-0001")

``process_many`` reads several files and lets an extractor that supports it (OpenDataLoader) convert them in one
engine call. Every chunk carries the configuration signature and the engine that read it."""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

from .chunkers import add_headers
from .config import PipelineConfig
from .extractors.base import Extractor, UnsupportedFormat
from .markdown import render_markdown
from .model import Chunk, NormalizedDocument
from .registry import CHUNKERS, EXTRACTORS, STEPS, TOKENIZERS
from .routes import read


@dataclass
class Result:
    path: Path
    document: NormalizedDocument
    chunks: list[Chunk]
    seconds: dict[str, float] = field(default_factory=dict)

    @property
    def markdown(self) -> str:
        return render_markdown(self.document)

    def summary(self) -> dict:
        kinds: dict[str, int] = {}
        for b in self.document.blocks:
            kinds[b.kind] = kinds.get(b.kind, 0) + 1
        tokens = [c.tokens for c in self.chunks]
        return {"file": self.path.name, "doc_id": self.document.doc_id, "title": self.document.title,
                "format": self.document.source_format, "pages": self.document.pages,
                "engine": self.document.meta.get("engine"), "route": self.document.meta.get("route"),
                "blocks": kinds, "dropped": len(self.document.meta.get("dropped", [])),
                "chunks": len(self.chunks), "tokens_min": min(tokens, default=0), "tokens_max": max(tokens, default=0),
                "tokens_mean": round(sum(tokens) / len(tokens), 1) if tokens else 0, "seconds": self.seconds}


def default_doc_id(path: Path) -> str:
    """Until the corpus manifest assigns ids, the first 16 hex of the file's SHA-256 (same file, same id)."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()[:16]


class Pipeline:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.signature = config.signature()
        self._extractors: dict[str, Extractor] = {}
        self.tokens = TOKENIZERS.create(config.tokens)
        self.steps = [STEPS.create(name, **config.step_options.get(name, {})) for name in config.steps]
        self.chunker = CHUNKERS.create(config.chunker.name, tokens=self.tokens, language=config.language,
                                       **config.chunker.params())

    def extractor_for(self, path: Path) -> Extractor:
        fmt = path.suffix.lower().lstrip(".")
        name = self.config.extractors.get(fmt)
        if name is None:
            raise UnsupportedFormat(f"No hay extractor configurado para .{fmt} "
                                    f"(configurados: {', '.join(sorted(self.config.extractors))})")
        if name not in self._extractors:
            self._extractors[name] = EXTRACTORS.create(name, **self.config.extractor_options.get(name, {}))
        return self._extractors[name]

    def read(self, path: Path, doc_id: str | None = None, title: str | None = None) -> NormalizedDocument:
        """``title``: the catalogue title (the corpus record); file metadata titles are often «Microsoft Word - …»."""
        doc = read(self.config.route, self.extractor_for(path), path, doc_id or default_doc_id(path))
        if title:
            doc = replace(doc, title=title)
        # pages with extractable text, counted on the raw extraction (before the steps drop bibliography or front
        # matter): the rest of the pages are the ones skipped because OCR is off
        text_pages = len({b.page for b in doc.blocks if b.page and b.text.strip()}) if doc.pages else None
        doc = replace(doc, meta={**doc.meta, "text_pages": text_pages})
        for step in self.steps:
            doc = step(doc)
        return doc.with_blocks(doc.blocks, steps=list(self.config.steps), signature=self.signature)

    def chunk(self, doc: NormalizedDocument) -> list[Chunk]:
        chunks = self.chunker(doc)
        if self.config.contextual_header:
            chunks = add_headers(doc, chunks, self.config.header)
        stamp = {"signature": self.signature, "engine": doc.meta.get("engine"), "route": doc.meta.get("route")}
        return [replace(c, meta={**c.meta, **stamp}) for c in chunks]

    def process(self, path: Path, doc_id: str | None = None, title: str | None = None) -> Result:
        t0 = time.perf_counter()
        doc = self.read(path, doc_id, title)
        t1 = time.perf_counter()
        chunks = self.chunk(doc)
        t2 = time.perf_counter()
        ext = self.extractor_for(path)
        if hasattr(ext, "release"):
            ext.release(path)
        return Result(path, doc, chunks, {"read": round(t1 - t0, 3), "chunk": round(t2 - t1, 3)})

    def process_many(self, paths: list[Path], doc_ids: dict[Path, str] | None = None,
                     titles: dict[Path, str] | None = None) -> list[Result]:
        by_extractor: dict[str, list[Path]] = {}
        for p in paths:
            by_extractor.setdefault(self.extractor_for(p).name, []).append(p)
        for name, group in by_extractor.items():
            ext = self._extractors[name]
            if hasattr(ext, "prepare"):
                ext.prepare(group)
        return [self.process(p, (doc_ids or {}).get(p), (titles or {}).get(p)) for p in paths]
