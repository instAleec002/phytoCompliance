"""The document corpus from the command line.

    uv run python -m interfaces.jobs.corpus descargar            # seed list -> dated snapshot + documents table
    uv run python -m interfaces.jobs.corpus indexar              # latest snapshot -> pipeline -> chunks -> vectors
    uv run python -m interfaces.jobs.corpus estado               # counter: documents by source and status, chunks, vectors
    uv run python -m interfaces.jobs.corpus preguntar "¿...?"    # retrieval and cited answer, as the API gives them

``indexar`` accepts the pipeline overrides of ``interfaces.jobs.documents`` (``--route``, ``--pdf``, ``--chunker``,
``--max-tokens``) and ``--embedder``; a different configuration is stored under its own signature, next to the others.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from knowledge.corpus.download import SOURCE, DocumentRecord, download_seed
from knowledge.corpus.sources import CONFIG, SeedItem, load_registry, load_seed
from knowledge.corpus.store import CorpusStore, connect, migrate
from knowledge.snapshots.store import latest
from shared.settings import REPO


def store() -> CorpusStore:
    conn = connect()
    migrate(conn)
    return CorpusStore(conn)


def descargar(args) -> None:
    registry, seed = load_registry(), load_seed()
    if args.lista == "completo":   # seed + curated selection (corpus seleccionar), without repeating items
        extra = load_seed(CONFIG / "corpus_completo.yaml")
        if (CONFIG / "corpus_recuperados.yaml").exists():   # relevant theses whose title does not name the crop
            extra += load_seed(CONFIG / "corpus_recuperados.yaml")
        known = {s.uuid for s in seed if s.uuid}
        seed = seed + [s for s in extra if s.uuid not in known]
        # every internal document of the local sources, not only the one in the seed list
        files = {s.file for s in seed if s.file}
        for key, src in registry.sources.items():
            if src.kind == "local":
                for p in sorted((REPO / src.folder).glob("*.docx")):
                    if p.name not in files:
                        seed.append(SeedItem(source=key, file=p.name, why="procedimiento interno del caso simulado"))
    folder, records = download_seed(registry, seed)
    st = store()
    st.upsert_documents(records, folder.name)
    for r in records:
        mark = "ok " if r.status == "descargado" else "-- "
        print(f"{mark}{r.doc_id:22} {r.level:7} {(r.title or '')[:70]}" + (f"   ({r.reason})" if r.reason else ""))
    print(f"instantánea: {folder}")


def seleccionar(args) -> None:
    from knowledge.corpus.discover import discover, select

    manifest = Path(args.manifiesto) if args.manifiesto else None
    if manifest is None:
        manifest = REPO / "non_local" / "non_data" / "raw" / "corpus" / f"candidatos_{date.today().isoformat()}.jsonl"
        print(json.dumps(discover(manifest), ensure_ascii=False, indent=1))
    print("selección:", select(manifest, CONFIG / "corpus_completo.yaml"))


def curar(args) -> None:
    from assistant.config import load_assistant_config
    from assistant.generation.generators import build_generator
    from knowledge.corpus.curate import curate

    folder = latest(SOURCE)
    if folder is None:
        raise SystemExit("No hay instantánea del corpus.")
    cfg = load_assistant_config()
    cfg.generators.setdefault("local", {})["think"] = False   # classification: no reasoning (Qwen3)
    summary = curate(Path(folder), build_generator(cfg.generator, cfg.generators, args.generador))
    records = json.loads((Path(folder) / "documents.json").read_text(encoding="utf-8"))
    store().upsert_documents([DocumentRecord(**r) for r in records], Path(folder).name)
    print(json.dumps(summary, ensure_ascii=False))


def recuperar(args) -> None:
    from assistant.config import load_assistant_config
    from assistant.generation.generators import build_generator
    from knowledge.corpus.discover import recover

    cfg = load_assistant_config()
    cfg.generators.setdefault("local", {})["think"] = False   # classification: no reasoning (Qwen3)
    print(json.dumps(recover(Path(args.manifiesto), build_generator(cfg.generator, cfg.generators, args.generador),
                             CONFIG / "corpus_recuperados.yaml"), ensure_ascii=False))


def estado(_args) -> None:
    print(json.dumps(store().status(), ensure_ascii=False, indent=1))


def indexar(args) -> None:
    from assistant.retrieval.indexing import index_snapshot

    folder = latest(SOURCE)
    if folder is None:
        raise SystemExit("No hay instantánea del corpus: corre primero «descargar».")
    summary = index_snapshot(store(), Path(folder), route=args.route, pdf=args.pdf, chunker=args.chunker,
                             max_tokens=args.max_tokens, embedder=args.embedder, only=args.solo,
                             encode=not args.diferido, min_tokens=args.min_tokens, child_tokens=args.child_tokens,
                             merge_section_tokens=args.merge_section_tokens,
                             header="short" if args.encabezado == "corto" else None,
                             table_rows=True if args.tablas_por_filas else None,
                             table_text="filas" if args.tablas_como_texto else None,
                             generic_sections="drop" if args.sin_genericas else None)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


WORK = REPO / "non_local" / "non_data" / "work"


def _signature(conn, wanted: str | None) -> str:
    if wanted:
        return wanted
    row = conn.execute("SELECT firma FROM indexaciones ORDER BY creada DESC LIMIT 1").fetchone()
    if not row:
        raise SystemExit("No hay indexaciones.")
    return row[0]


def vectores_exportar(args) -> None:
    """Chunks without a vector -> a job folder for the GPU machine (textos.jsonl + ml/embedding/encode.py)."""
    import shutil

    st = store()
    sig = _signature(st.conn, args.firma)
    rows = st.pending_embeddings(sig, args.modelo)
    folder = WORK / f"vectores_{sig}"
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    with open(folder / "textos.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps({"chunk_id": cid, "text": text}, ensure_ascii=False) + "\n" for cid, text in rows)
    shutil.copy(REPO / "ml" / "embedding" / "encode.py", folder / "encode.py")
    print(json.dumps({"firma": sig, "pendientes": len(rows), "carpeta": str(folder)}, ensure_ascii=False))


def vectores_importar(args) -> None:
    """salida/ of the encode job -> pgvector, under the signature and the encoder's name."""
    import numpy as np

    folder = Path(args.carpeta)
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    ids = json.loads((folder / "ids.json").read_text(encoding="utf-8"))
    vecs = np.load(folder / "vectores.npy")
    sig = args.firma or folder.parent.name.removeprefix("vectores_")
    model = meta["modelo"].split("/")[-1].lower()
    st = store()
    for k in range(0, len(ids), 500):
        st.save_vectors(sig, model, [(cid, v.tolist()) for cid, v in zip(ids[k:k + 500], vecs[k:k + 500], strict=True)])
    print(json.dumps({"firma": sig, "modelo": model, "importados": len(ids), "pendientes": len(st.pending_embeddings(sig, model)),
                      "segundos_gpu": meta["segundos"]}, ensure_ascii=False))


def preguntar(args) -> None:
    from assistant.answer import build_answerer

    answerer = build_answerer(store(), generator=args.generador)
    result = answerer.answer(args.pregunta)
    print(result.text)
    print()
    for c in result.citations:
        print(f"[{c.n}] {c.title} | {' > '.join(c.section)} | p. {','.join(map(str, c.pages)) or '-'} | {c.url}")
    print(json.dumps(result.trace, ensure_ascii=False, indent=1))


def main() -> None:
    parser = argparse.ArgumentParser(prog="interfaces.jobs.corpus")
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("descargar", help="descarga la lista (semilla o completa) en una instantánea fechada")
    d.add_argument("--lista", choices=["semilla", "completo"], default="semilla")
    s = sub.add_parser("seleccionar", help="cuenta candidatos en DSpace y escribe config/corpus_completo.yaml")
    s.add_argument("--manifiesto", help="usar un manifiesto de candidatos ya generado")
    c = sub.add_parser("curar", help="clasifica por alcance los documentos académicos de la última instantánea")
    c.add_argument("--generador", default="gemini", help="gemini o local (Qwen3-8B en el equipo con GPU)")
    r = sub.add_parser("recuperar", help="clasifica las tesis cuyo título no nombra el cultivo y escribe corpus_recuperados.yaml")
    r.add_argument("manifiesto", help="manifiesto de candidatos (candidatos_<fecha>.jsonl)")
    r.add_argument("--generador", default="local")
    sub.add_parser("estado", help="contador del corpus")
    p = sub.add_parser("indexar", help="procesa, trocea e indexa la última instantánea")
    p.add_argument("--route", choices=["markdown", "structured", "mixed"])
    p.add_argument("--pdf")
    p.add_argument("--chunker")
    p.add_argument("--max-tokens", type=int)
    p.add_argument("--embedder")
    p.add_argument("--solo", nargs="*", help="solo estos doc_id")
    p.add_argument("--diferido", action="store_true", help="guarda los fragmentos sin vectores (se codifican en el equipo con GPU)")
    # variantes de troceado (etapa 3); cada combinación queda con su propia firma
    p.add_argument("--min-tokens", type=int)
    p.add_argument("--child-tokens", type=int, help="parent_child: tamaño de los hijos")
    p.add_argument("--unir-secciones", type=int, dest="merge_section_tokens", help="V2: une secciones de menos de N tokens con la siguiente del mismo padre")
    p.add_argument("--encabezado", choices=["completo", "corto"], help="V3: corto = título y los dos últimos niveles")
    p.add_argument("--tablas-por-filas", action="store_true", help="V6: parte las tablas grandes por filas repitiendo el encabezado")
    p.add_argument("--tablas-como-texto", action="store_true", help="V6b: el codificador lee las tablas como una oración por fila (el usuario ve la tabla)")
    p.add_argument("--sin-genericas", action="store_true", help="solo para comparar: no indexa resumen, introducción, conclusiones…")
    e = sub.add_parser("vectores-exportar", help="fragmentos sin vector -> carpeta de trabajo para el equipo con GPU")
    e.add_argument("--firma")
    e.add_argument("--modelo", default="bge-m3")
    i = sub.add_parser("vectores-importar", help="carga en pgvector los vectores codificados en el equipo con GPU")
    i.add_argument("carpeta", help="carpeta salida/ traída del equipo con GPU")
    i.add_argument("--firma")
    q = sub.add_parser("preguntar", help="pregunta al asistente")
    q.add_argument("pregunta")
    q.add_argument("--generador")
    args = parser.parse_args()
    {"descargar": descargar, "seleccionar": seleccionar, "curar": curar, "recuperar": recuperar, "estado": estado, "indexar": indexar, "preguntar": preguntar,
     "vectores-exportar": vectores_exportar, "vectores-importar": vectores_importar}[args.command](args)


if __name__ == "__main__":
    main()
