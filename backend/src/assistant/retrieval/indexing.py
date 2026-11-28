"""Indexing: a corpus snapshot through the document pipeline into chunks and vectors.

Each source gets the pipeline configuration plus its own rules (``rules`` step with the source's options, after
``sections``), so a thesis loses its bibliography while a manual keeps everything. Chunks are stored under the
pipeline signature; the embeddable ones (all but ``parent`` chunks) are encoded with their contextual header
(``embedding_text``) and stored under the encoder's name. A document that fails is marked ``fallido`` with the error
and the run continues. The run is recorded in ``indexaciones``."""
from __future__ import annotations

import json
import time
from pathlib import Path

from assistant.config import load_assistant_config
from knowledge.corpus.sources import load_registry
from knowledge.corpus.store import CorpusStore
from knowledge.documents import Pipeline, load_config

from .embeddings import build_embedder


def index_snapshot(store: CorpusStore, folder: Path, route: str | None = None, pdf: str | None = None,
                   chunker: str | None = None, max_tokens: int | None = None, embedder: str | None = None,
                   only: list[str] | None = None, encode: bool = True, **variant) -> dict:
    """``encode=False`` stores the chunks without vectors (deferred encoding on the GPU machine: corpus vectores-exportar,
    gpu_job, corpus vectores-importar); the encoder is not even loaded. `variant`: stage 3 options passed to the
    configuration (`merge_section_tokens`, `generic_sections`, `table_rows`, `header`, `min_tokens`,
    `child_tokens`); each combination gets its own signature."""
    t0 = time.perf_counter()
    registry = load_registry()
    base = load_config(route=route, pdf=pdf, chunker=chunker, max_tokens=max_tokens, **variant)
    acfg = load_assistant_config()
    if embedder:
        acfg.embedder.name = embedder
    enc = build_embedder(acfg.embedder) if encode else None
    enc_name = enc.name if enc else acfg.embedder.model.split("/")[-1].lower()
    records = [r for r in json.loads((folder / "documents.json").read_text(encoding="utf-8")) if r["status"] == "descargado"]
    if only:
        records = [r for r in records if r["doc_id"] in only]

    by_source: dict[str, list[dict]] = {}
    for r in records:
        by_source.setdefault(r["source"], []).append(r)

    signature = base.signature()
    totals = {"documentos": 0, "fragmentos": 0, "vectores": 0, "fallidos": []}
    for source, recs in by_source.items():
        rules = registry.sources[source].rules
        cfg = base if not rules else base.model_copy(update={
            "steps": [*base.steps, "rules"], "step_options": {**base.step_options, "rules": rules}})
        pipeline = Pipeline(cfg)
        # the stored signature is the base one: per-source rules are part of the corpus definition, not a variant
        paths = {folder / r["file"]: r for r in recs}
        ext_groups: dict[str, list[Path]] = {}
        for p in paths:
            ext_groups.setdefault(pipeline.extractor_for(p).name, []).append(p)
        for name, group in ext_groups.items():
            ext = pipeline._extractors[name]
            if hasattr(ext, "prepare"):
                try:
                    ext.prepare(group)
                except Exception as e:  # noqa: BLE001 - a failing batch falls back to one file at a time
                    print(f"  conversión por lotes de {name} falló ({type(e).__name__}); se lee archivo por archivo",
                          flush=True)
        for path, rec in paths.items():
            try:
                res = pipeline.process(path, rec["doc_id"], rec["title"])
                chunks = res.chunks
                if not chunks:
                    # a scanned PDF without a text layer: nothing to index while OCR is off
                    store.set_status(rec["doc_id"], "excluido", reason="sin texto extraíble (PDF escaneado; OCR apagado)",
                                     pages=res.document.pages, fmt=res.document.source_format,
                                     text_pages=res.document.meta.get("text_pages"))
                    totals["sin_texto"] = totals.get("sin_texto", 0) + 1
                    print(f"  {rec['doc_id']:24}    0 fragmentos  (sin texto: escaneado)", flush=True)
                    continue
                store.replace_chunks(rec["doc_id"], signature, chunks)
                embeddable = [c for c in chunks if c.meta.get("role", "atomic") != "parent"]
                vectors = enc.encode([c.embedding_text for c in embeddable]) if (embeddable and enc) else []
                if vectors:
                    store.save_vectors(signature, enc.name, list(zip([c.chunk_id for c in embeddable], vectors, strict=True)))
                store.set_status(rec["doc_id"], "indexado", pages=res.document.pages, fmt=res.document.source_format,
                                 text_pages=res.document.meta.get("text_pages"))
                totals["documentos"] += 1
                totals["fragmentos"] += len(chunks)
                totals["vectores"] += len(vectors)
                print(f"  {rec['doc_id']:24} {len(chunks):4} fragmentos  {res.seconds['read']:6.1f} s", flush=True)
            except Exception as e:  # noqa: BLE001 - record and continue with the rest of the corpus
                store.set_status(rec["doc_id"], "fallido", reason=f"{type(e).__name__}: {e}"[:500])
                totals["fallidos"].append(rec["doc_id"])
                print(f"  {rec['doc_id']:24} FALLÓ: {type(e).__name__}: {e}", flush=True)
    seconds = round(time.perf_counter() - t0, 1)
    store.record_run(signature, enc_name, {"pipeline": base.model_dump(), "embedder": acfg.embedder.model_dump()},
                     totals["documentos"], totals["fragmentos"], seconds)
    return {"firma": signature, "codificador": enc_name, "vectores_diferidos": not encode, "segundos": seconds, **totals}
