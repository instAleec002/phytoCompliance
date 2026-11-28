"""Process documents with any pipeline configuration and write what each stage produced, to inspect or compare.

    uv run python -m interfaces.jobs.documents procesar <file or folder>... [--route markdown|structured|mixed]
        [--pdf opendataloader|pymupdf|docling] [--docx docx|docling] [--xlsx xlsx|docling]
        [--chunker structural|fixed|page|parent_child] [--max-tokens N] [--header on|off] [--out DIR]

For each file, ``<out>/<signature>/<stem>/`` receives:
- ``blocks.json``: the normalized document (blocks with kind, page, level and section; what was dropped and why);
- ``document.md``: its Markdown rendering with page anchors;
- ``chunks.jsonl``: one chunk per line (text, header, pages, section, tokens, role);
- ``summary.json``: counts, token statistics and times.
``<out>/<signature>/config.json`` records the full configuration, so a folder is always reproducible. The default
output is ``non_local/non_data/documents/runs``.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from knowledge.documents import Pipeline, load_config
from shared.settings import REPO

FORMATS = {".pdf", ".docx", ".xlsx"}
DEFAULT_OUT = REPO / "non_local" / "non_data" / "documents" / "runs"


def _files(inputs: list[str]) -> list[Path]:
    out = []
    for raw in inputs:
        p = Path(raw)
        if p.is_dir():
            out += sorted(f for f in p.rglob("*") if f.suffix.lower() in FORMATS)
        elif p.suffix.lower() in FORMATS:
            out.append(p)
        else:
            raise SystemExit(f"No es PDF, DOCX ni XLSX: {p}")
    return out


def procesar(args) -> None:
    cfg = load_config(route=args.route, pdf=args.pdf, docx=args.docx, xlsx=args.xlsx, chunker=args.chunker,
                      max_tokens=args.max_tokens,
                      contextual_header=None if args.header is None else args.header == "on")
    pipeline = Pipeline(cfg)
    root = Path(args.out) / pipeline.signature
    root.mkdir(parents=True, exist_ok=True)
    (root / "config.json").write_text(json.dumps(cfg.model_dump(), ensure_ascii=False, indent=1), encoding="utf-8")
    files = _files(args.inputs)
    print(f"configuración {pipeline.signature}: ruta {cfg.route}, extractores {cfg.extractors}, "
          f"troceador {cfg.chunker.name} ({cfg.chunker.max_tokens} tokens), encabezado {'sí' if cfg.contextual_header else 'no'}")
    for result in pipeline.process_many(files):
        folder = root / result.path.stem
        folder.mkdir(parents=True, exist_ok=True)
        doc = result.document
        (folder / "blocks.json").write_text(json.dumps(
            {"doc_id": doc.doc_id, "title": doc.title, "format": doc.source_format, "pages": doc.pages, "meta": doc.meta,
             "blocks": [asdict(b) for b in doc.blocks]}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        (folder / "document.md").write_text(result.markdown, encoding="utf-8")
        with (folder / "chunks.jsonl").open("w", encoding="utf-8") as f:
            for c in result.chunks:
                f.write(json.dumps({**asdict(c), "embedding_text": c.embedding_text}, ensure_ascii=False, default=str) + "\n")
        summary = result.summary()
        (folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {result.path.name}: {summary['chunks']} fragmentos, {sum(summary['blocks'].values())} bloques, "
              f"{summary['dropped']} descartados, {summary['seconds']['read']} s de lectura")
    print(f"salida: {root}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="interfaces.jobs.documents")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("procesar", help="procesa archivos o carpetas con la configuración dada")
    p.add_argument("inputs", nargs="+")
    p.add_argument("--route", choices=["markdown", "structured", "mixed"])
    p.add_argument("--pdf")
    p.add_argument("--docx")
    p.add_argument("--xlsx")
    p.add_argument("--chunker")
    p.add_argument("--max-tokens", type=int)
    p.add_argument("--header", choices=["on", "off"])
    p.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    if args.command == "procesar":
        procesar(args)


if __name__ == "__main__":
    main()
