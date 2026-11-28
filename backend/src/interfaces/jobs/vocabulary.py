"""The controlled vocabulary (stage 4).

    uv run python -m interfaces.jobs.vocabulary descargar        # graph terms -> AGROVOC snapshot (slow, polite)
    uv run python -m interfaces.jobs.vocabulary estado           # terms, concepts and labels per kind
    uv run python -m interfaces.jobs.vocabulary expandir "¿Cómo controlo la oidiosis en vid?"
    uv run python -m interfaces.jobs.vocabulary menciones [--firma F]   # graph terms each fragment names (D4)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

CROPS = {"blueberry": ["Vaccinium corymbosum", "blueberries"], "avocado": ["Persea americana", "avocados"],
         "table_grape": ["Vitis vinifera", "table grapes", "grapes"]}


def _graph_terms():
    from knowledge.graph.age import AgeGraph

    with AgeGraph.connect() as g:
        pests = g.run("MATCH (p:Pest) WHERE p.other_use = false RETURN p.key, p.scientific_name, p.common_name",
                      columns=("k", "s", "c"))
        ings = [r[0] for r in g.run("MATCH (i:Ingredient) RETURN i.key")]
    return pests, ings


def _spanish_ingredients() -> dict[str, str]:
    import yaml

    from knowledge.corpus.sources import CONFIG
    from knowledge.normalization.ingredients import Aliases, spanish_names

    es = spanish_names(Aliases.load())
    extra = yaml.safe_load((CONFIG / "ingredient_nombres_es.yaml").read_text(encoding="utf-8")) or {}
    es.update({k: v["es"] for k, v in extra.items() if v.get("es")})
    return es


def load_vocabulary():
    from knowledge.snapshots.store import latest
    from knowledge.vocabulary.index import Vocabulary

    pests, _ = _graph_terms()
    folder = latest("agrovoc")
    return Vocabulary.build(Path(folder) if folder else None, pests, _spanish_ingredients())


def descargar(_args) -> None:
    from knowledge.vocabulary.agrovoc import download

    pests, ings = _graph_terms()
    terms = [{"kind": "crop", "key": k, "query": q} for k, q in CROPS.items()]
    terms += [{"kind": "pest", "key": k, "query": [(s or "").strip()]} for k, s, _ in pests if s and s.strip()]
    terms += [{"kind": "ingredient", "key": i, "query": [i]} for i in ings]
    snap, counts = download(terms)
    print(json.dumps({"instantanea": str(snap.folder), **counts}, ensure_ascii=False))


def estado(_args) -> None:
    print(json.dumps(load_vocabulary().stats(), ensure_ascii=False, indent=1))


def expandir(args) -> None:
    v = load_vocabulary()
    print(json.dumps({"terminos": [f"{t.kind}:{t.key}" for t in v.find(args.texto)], "sinonimos": v.expand(args.texto)},
                     ensure_ascii=False, indent=1))


PARES = Path(__file__).resolve().parents[4] / "ml" / "adaptation" / "bge_m3_lora" / "data" / "sinonimos.jsonl"


def pares(args) -> None:
    """Synonym pairs for the encoder's LoRA (stage 9), next to its train.jsonl."""
    rows = load_vocabulary().pairs(args.por_termino)
    out = Path(args.salida)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    kinds = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    print(json.dumps({"pares": len(rows), "por_tipo": kinds, "archivo": str(out)}, ensure_ascii=False))


def menciones(args) -> None:
    """Fills ``menciones`` for one index signature (the deployed one by default): the graph terms each fragment's text names,
    with the vocabulary index. Rebuilt from scratch for that signature, so it can be run again after a reindex."""
    from assistant.config import load_assistant_config
    from assistant.retrieval.search import latest_signature
    from knowledge.corpus.store import connect, migrate

    conn = connect()
    migrate(conn)
    cfg = load_assistant_config()
    firma = args.firma or (cfg.retrieval.signature if cfg.retrieval.signature != "latest"
                           else latest_signature(conn, cfg.embedder.name))
    v = load_vocabulary()
    filas = conn.execute("SELECT chunk_id, doc_id, texto FROM fragmentos WHERE firma = %s AND rol <> 'parent'",
                         (firma,)).fetchall()
    rows = [(firma, cid, doc, kind, key) for cid, doc, texto in filas for kind, key in sorted(v.mentions(texto))]
    with conn.transaction():
        conn.execute("DELETE FROM menciones WHERE firma = %s", (firma,))
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO menciones (firma, chunk_id, doc_id, tipo, clave) VALUES (%s, %s, %s, %s, %s)",
                            rows)
    por_tipo = {}
    for r in rows:
        por_tipo[r[3]] = por_tipo.get(r[3], 0) + 1
    print(json.dumps({"firma": firma, "fragmentos": len(filas), "menciones": len(rows),
                      "fragmentos_con_mencion": len({r[1] for r in rows}), "por_tipo": por_tipo}, ensure_ascii=False))


def main() -> None:
    p = argparse.ArgumentParser(prog="interfaces.jobs.vocabulary")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("descargar")
    sub.add_parser("estado")
    e = sub.add_parser("expandir")
    e.add_argument("texto")
    pa = sub.add_parser("pares", help="pares de sinónimos para el LoRA del codificador (etapa 9)")
    pa.add_argument("--por-termino", type=int, default=6)
    pa.add_argument("--salida", default=str(PARES))
    m = sub.add_parser("menciones", help="etapa D4: términos del grafo que nombra cada fragmento")
    m.add_argument("--firma", help="firma del índice (por defecto la desplegada)")
    args = p.parse_args()
    {"descargar": descargar, "estado": estado, "expandir": expandir, "pares": pares,
     "menciones": menciones}[args.command](args)


if __name__ == "__main__":
    main()
