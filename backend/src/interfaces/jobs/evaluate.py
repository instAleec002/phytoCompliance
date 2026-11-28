"""Evaluation runs.

    uv run python -m interfaces.jobs.evaluate piloto-textual [--por-documento 3] [--reusar]

Builds (or reuses with --reusar) the pilot textual set in ml/evaluation/suites/textual_piloto.jsonl and writes the run
to ml/evaluation/runs/<date>_textual_piloto/: retrieval metrics per retriever, end-to-end metrics, every answer, and
the configuration (index signature, encoder, generator, judge).
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict
from datetime import datetime

from shared.settings import REPO

SUITES = REPO / "ml" / "evaluation" / "suites"
RUNS = REPO / "ml" / "evaluation" / "runs"


def piloto_textual(args) -> None:
    from assistant.answer import build_answerer
    from assistant.config import load_assistant_config
    from assistant.generation.generators import build_generator
    from evaluation.textual import PilotItem, build_pilot, end_to_end, retrieval_metrics
    from knowledge.corpus.store import CorpusStore, connect, migrate

    conn = connect()
    migrate(conn)
    store = CorpusStore(conn)
    cfg = load_assistant_config()
    answerer = build_answerer(store, cfg)
    retriever = answerer.retriever
    llm = build_generator(cfg.generator, cfg.generators, "gemini")

    SUITES.mkdir(parents=True, exist_ok=True)
    suite = SUITES / "textual_piloto.jsonl"
    if args.reusar and suite.exists():
        items = [PilotItem(**json.loads(line)) for line in suite.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        items = build_pilot(conn, retriever.signature, llm, per_doc=args.por_documento)
        suite.write_text("\n".join(json.dumps(asdict(i), ensure_ascii=False) for i in items) + "\n", encoding="utf-8")
    print(f"preguntas: {sum(i.in_scope for i in items)} del corpus y {sum(not i.in_scope for i in items)} fuera de él")

    retrieval = retrieval_metrics(conn, retriever, items)
    print(json.dumps(retrieval, indent=1))
    summary, records = end_to_end(answerer, llm, items)
    print(json.dumps(summary, indent=1))

    run = RUNS / f"{datetime.now():%Y-%m-%d_%H%M}_textual_piloto"
    run.mkdir(parents=True, exist_ok=True)
    (run / "metricas.json").write_text(json.dumps({
        "suite": str(suite.relative_to(REPO)), "signature": retriever.signature, "encoder": retriever.embedder.name,
        "generator": answerer.generator.name, "judge": llm.name, "retrieval": retrieval, "end_to_end": summary},
        ensure_ascii=False, indent=1), encoding="utf-8")
    (run / "respuestas.jsonl").write_text("\n".join(json.dumps(asdict(r), ensure_ascii=False) for r in records) + "\n",
                                          encoding="utf-8")
    print(f"corrida: {run}")


def suite_estructurada(args) -> None:
    """S1: at least 100 questions with an exact answer taken from the graph (official snapshots)."""
    from collections import Counter
    from datetime import date

    from evaluation.structured import build_suite
    from knowledge.graph.age import AgeGraph

    day = date.fromisoformat(args.fecha) if args.fecha else date.today()
    with AgeGraph.connect() as g:
        items = build_suite(g, day)
    out = SUITES / "estructurada.jsonl"
    out.write_text("\n".join(json.dumps(i, ensure_ascii=False) for i in items) + "\n", encoding="utf-8")
    print(json.dumps({"preguntas": len(items), "por_tipo": dict(Counter(i["tipo"] for i in items)),
                      "grafia": dict(Counter(i["parametros"].get("grafia") for i in items if "grafia" in i["parametros"])),
                      "fecha": day.isoformat(), "archivo": str(out)}, ensure_ascii=False))


def suite_programas(args) -> None:
    """S3: spray programs with seeded violations (at least 20)."""
    from collections import Counter

    from evaluation.programs import build_program_suite
    from interfaces.api.sources import graph_sources

    gen = graph_sources()
    sources = next(gen)
    try:
        cases = build_program_suite(sources.limits.graph, sources, args.n)
    finally:
        gen.close()
    out = SUITES / "programas.jsonl"
    out.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n", encoding="utf-8")
    print(json.dumps({"programas": len(cases), "por_cultivo": dict(Counter(c["cultivo"] for c in cases)),
                      "violaciones": dict(Counter(s["code"] for c in cases for s in c["sembradas"])),
                      "con_colaterales": sum(1 for c in cases if c["colaterales"]), "archivo": str(out)}, ensure_ascii=False))


def suite_textual(args) -> None:
    """S2: textual questions tied to a document, a page and a literal span (SENASA and UNALM), 1/3 multi-hop."""
    from collections import Counter
    from pathlib import Path

    from assistant.config import load_assistant_config
    from assistant.generation.generators import build_generator
    from evaluation.textual_suite import as_rows, build
    from interfaces.jobs.vocabulary import load_vocabulary
    from knowledge.snapshots.store import latest

    folder = Path(latest("corpus"))
    records = json.loads((folder / "documents.json").read_text(encoding="utf-8"))
    cfg = load_assistant_config()
    cfg.generators.setdefault("local", {})["think"] = False
    gen = build_generator(cfg.generator, cfg.generators, args.generador)
    items, docs = build(records, folder, gen, load_vocabulary(), args.un_salto, args.varios_saltos)
    (SUITES / "textual.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in as_rows(items)) + "\n",
                                         encoding="utf-8")
    (SUITES / "textual_documentos.json").write_text(json.dumps({"instantanea": folder.name, "documentos": docs,
                                                                "nota": "excluir de los datos de entrenamiento"},
                                                               ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"preguntas": len(items), "por_tipo": dict(Counter(i.tipo for i in items)),
                      "documentos": len(docs), "generador": gen.name}, ensure_ascii=False))


def recuperacion_s2(args) -> None:
    """Retrieval on S2 for the current index (or --firma), with the lexical ranking given by --ranking."""
    from assistant.answer import build_answerer
    from assistant.config import load_assistant_config
    from evaluation.textual_retrieval import evaluate
    from knowledge.corpus.store import CorpusStore, connect, migrate

    conn = connect()
    migrate(conn)
    cfg = load_assistant_config()
    cfg.retrieval.top_k = 10
    if args.firma:
        cfg.retrieval.signature = args.firma
    for ranking in args.ranking:
        cfg.retrieval.lexical_ranking = ranking
        retriever = build_answerer(CorpusStore(conn), cfg, "extractive").retriever
        items = [json.loads(line) for line in (SUITES / "textual.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        summary, records = evaluate(conn, retriever, items)
        run = RUNS / f"{datetime.now():%Y-%m-%d_%H%M}_recuperacion_s2_{ranking}"
        run.mkdir(parents=True, exist_ok=True)
        meta = {"suite": "ml/evaluation/suites/textual.jsonl", "firma": retriever.signature, "codificador": retriever.embedder.name,
                "ranking_lexico": ranking, "pesos_rrf": [retriever.lexical_weight, retriever.dense_weight], **summary}
        (run / "metricas.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        (run / "por_pregunta.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
                                                encoding="utf-8")
        print(ranking, json.dumps({k: {m: v for m, v in summary[k].items() if m != "por_tipo"}
                                   for k in ("lexico", "denso", "hibrido")}, ensure_ascii=False))


JUICIOS = SUITES / "juicios_s2.jsonl"


def _s2_items() -> list[dict]:
    return [json.loads(line) for line in (SUITES / "textual.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]


PARTICION = SUITES / "particion_s2.json"
SEMILLA_PARTICION = 20261124


def split_s2(items: list[dict], dev_share: float = 0.3, seed: int = SEMILLA_PARTICION) -> dict[str, list[str]]:
    """Development/test split of S2, stratified by question type and fixed by a seed (the protocol's 30/70).

    Within each type, questions are ordered by a hash of seed and qid, so the split does not depend on file order."""
    import hashlib

    dev, test = [], []
    for tipo in sorted({it["tipo"] for it in items}):
        qids = sorted((it["qid"] for it in items if it["tipo"] == tipo),
                      key=lambda q: hashlib.sha256(f"{seed}:{q}".encode()).hexdigest())
        n = round(dev_share * len(qids))
        dev += qids[:n]
        test += qids[n:]
    return {"semilla": seed, "desarrollo": sorted(dev), "prueba": sorted(test)}


def _particion(items: list[dict], nombre: str) -> list[dict]:
    """The questions of one split. The split is written once to suites/particion_s2.json and read from there after."""
    if nombre == "todo":
        return items
    if PARTICION.exists():
        split = json.loads(PARTICION.read_text(encoding="utf-8"))
    else:
        split = split_s2(items)
        PARTICION.write_text(json.dumps(split, ensure_ascii=False, indent=1), encoding="utf-8")
    keep = set(split[nombre])
    return [it for it in items if it["qid"] in keep]


def _retrievers(conn, rankings=("idf", "ts_rank"), firma=None, peso_genericas=None, encabezado_lexico=None, mmr=None,
               expandir=None, tope=None, lista_grafo=None, salto_entidad=False) -> dict:
    from assistant.answer import build_answerer
    from assistant.config import load_assistant_config
    from knowledge.corpus.store import CorpusStore

    out = {}
    for ranking in rankings:
        cfg = load_assistant_config()
        cfg.retrieval.top_k = 20
        cfg.retrieval.lexical_ranking = ranking
        if firma:
            cfg.retrieval.signature = firma
        if peso_genericas is not None:
            cfg.retrieval.generic_weight = peso_genericas
        if encabezado_lexico:
            cfg.retrieval.lexical_header = encabezado_lexico
        if mmr is not None:
            cfg.retrieval.mmr_lambda = mmr
        if expandir is not None:
            cfg.retrieval.expand_synonyms = expandir
        if tope is not None:                      # D1 (27/11/2026): fragments per document (0 = off)
            cfg.retrieval.max_per_document = tope or None
        if lista_grafo is not None:               # D3 (27/11/2026): weight of the graph list (0 = off)
            cfg.retrieval.graph_list_weight = lista_grafo or None
        cfg.retrieval.entity_hop = bool(salto_entidad)  # D4 (27/11/2026)
        out[ranking] = build_answerer(CorpusStore(conn), cfg, "extractive").retriever
    return out


def juicios_s2(args) -> None:
    """Pool the top fragments of every configuration and grade them (span page = 2, the rest by the Qwen judge)."""
    from assistant.config import load_assistant_config
    from assistant.generation.generators import build_generator
    from evaluation.judgments import Judgments, judge_pool
    from knowledge.corpus.store import connect, migrate

    conn = connect()
    migrate(conn)
    cfg = load_assistant_config()
    cfg.generators.setdefault("local", {})["think"] = False
    judge = build_generator(cfg.generator, cfg.generators, args.generador)
    store = Judgments(JUICIOS)
    retrievers = _retrievers(conn, firma=args.firma, peso_genericas=args.peso_genericas, lista_grafo=args.lista_grafo,
                             salto_entidad=args.salto_entidad)
    if args.descomponer:                     # etapa 5: el pool incluye lo que traen las subpreguntas
        from assistant.orchestration.subpreguntas import Descomponedor, RecuperadorMultipregunta
        local = cfg.generators.get("local", {})
        d = Descomponedor(local.get("base_url", "http://localhost:11434/v1"), local.get("model", "qwen3:8b"))
        retrievers = {k: RecuperadorMultipregunta(r, d) for k, r in retrievers.items()}
    stats = judge_pool(conn, retrievers, _s2_items(), judge, store, args.profundidad,
                       log=lambda m: print(m, flush=True))
    grades = [r["grado"] for r in store.rows]
    print(json.dumps({**stats, "total": len(store.rows), "grado_2": grades.count(2), "grado_1": grades.count(1),
                      "grado_0": grades.count(0), "juez": judge.name}, ensure_ascii=False))


def juicios_muestra(args) -> None:
    from evaluation.judgments import Judgments, sample_for_annotation
    from knowledge.corpus.store import connect

    conn = connect()
    titles = dict(conn.execute("SELECT doc_id, titulo FROM documentos").fetchall())
    out = SUITES / "juicios_s2_muestra_anotacion.xlsx"
    n = sample_for_annotation(Judgments(JUICIOS), {i["qid"]: i["pregunta"] for i in _s2_items()}, titles, out, args.n)
    print(f"{n} juicios en {out}")


def juicios_kappa(args) -> None:
    from pathlib import Path

    from evaluation.judgments import Judgments, agreement

    res = agreement(Judgments(JUICIOS), Path(args.archivo))
    res = {"fecha": __import__("datetime").date.today().isoformat(), "muestra": Path(args.archivo).name, **res}
    (SUITES / "juicios_s2_kappa.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False))


def recuperacion_juzgada(args) -> None:
    """Graded metrics (Recall@k, util@k, MRR@10, nDCG@10) over the judgment pool, per configuration and list."""
    import statistics

    from evaluation.judgments import Judgments, fragments, graded_metrics
    from knowledge.corpus.store import connect, migrate

    conn = connect()
    migrate(conn)
    store = Judgments(JUICIOS)
    items = _particion(_s2_items(), args.particion)
    results, por_pregunta = {}, []
    descomponer = None
    if args.descomponer:
        from assistant.config import load_assistant_config
        from assistant.orchestration.subpreguntas import Descomponedor, RecuperadorMultipregunta
        local = load_assistant_config().generators.get("local", {})
        descomponer = Descomponedor(local.get("base_url", "http://localhost:11434/v1"), local.get("model", "qwen3:8b"))
    for ranking, r in _retrievers(conn, args.ranking, args.firma, args.peso_genericas, args.encabezado_lexico, args.mmr,
                                         {"si": True, "no": False}.get(args.expandir), args.tope,
                                         args.lista_grafo, args.salto_entidad).items():
        if descomponer:                                           # etapa 5: subpreguntas fundidas con RRF
            r = RecuperadorMultipregunta(r, descomponer)
        lists = {"lexico": lambda q, r=r: r.lexical(q)[:10], "denso": lambda q, r=r: [c for c, _ in r.dense(q)][:10],
                 "hibrido": lambda q, r=r: [p.chunk_id for p in r.retrieve(q)][:10]}
        for name, fn in lists.items():
            if name == "denso" and "denso" in {k.split("/")[1] for k in results}:
                continue                       # the dense list does not depend on the lexical ranking
            per = []
            for it in items:
                ids = fn(it["pregunta"])
                frs = fragments(conn, r.signature, ids)
                ranked = [(frs[c]["doc_id"], frs[c]["paginas"], frs[c]["texto"]) for c in ids if c in frs]
                per.append({"tipo": it["tipo"], **graded_metrics(ranked, it["qid"], store)})
                por_pregunta.append({"lista": f"{ranking}/{name}", "qid": it["qid"], **per[-1],
                                     **({"subpreguntas": r.ultimas} if descomponer and name == "hibrido" else {})})
            keys = [k for k in per[0] if k != "tipo"]
            results[f"{ranking}/{name}"] = {
                **{k: round(statistics.fmean(p[k] for p in per), 3) for k in keys},
                "por_tipo": {t: {k: round(statistics.fmean(p[k] for p in per if p["tipo"] == t), 3) for k in keys}
                             for t in sorted({p["tipo"] for p in per})}}
    run = RUNS / f"{datetime.now():%Y-%m-%d_%H%M}_recuperacion_juzgada"
    run.mkdir(parents=True, exist_ok=True)
    opciones = {"particion": args.particion, "preguntas": len(items), "mmr": args.mmr,
                "encabezado_lexico": args.encabezado_lexico or "con", "peso_genericas": args.peso_genericas,
                "tope_por_documento": args.tope, "lista_grafo": args.lista_grafo, "salto_entidad": args.salto_entidad,
                "expandir_sinonimos": args.expandir, "descomponer": bool(args.descomponer)}
    (run / "metricas.json").write_text(json.dumps({"juicios": len(store.rows), "firma": r.signature, **opciones, **results},
                                                  ensure_ascii=False, indent=1), encoding="utf-8")
    # per question, for paired tests between configurations (Wilcoxon, bootstrap)
    (run / "por_pregunta.jsonl").write_text("\n".join(json.dumps(p, ensure_ascii=False) for p in por_pregunta) + "\n",
                                            encoding="utf-8")
    for k, v in results.items():
        print(k, {m: x for m, x in v.items() if m != "por_tipo"}, "| varios saltos util@10:",
              v["por_tipo"].get("varios_saltos", {}).get("util@10"))


def _resumen_fidelidad(filas: list[dict], **extra) -> dict:
    import statistics

    from evaluation.fidelidad import VEREDICTOS

    medidas = [x["fidelidad"] for x in filas if x["fidelidad"] is not None]
    por_tipo = {}
    for t in sorted({str(x["tipo"]) for x in filas}):
        v = [x["fidelidad"] for x in filas if str(x["tipo"]) == t and x["fidelidad"] is not None]
        por_tipo[t] = {"n": len(v), "media": round(statistics.mean(v), 3) if v else None}
    frases = [v for x in filas for v in (x.get("veredictos") or [])]
    return {**extra, "preguntas": len(filas), "con_evidencia": sum(1 for x in filas if x["evidencia"]),
            "abstenciones": sum(1 for x in filas if not x["evidencia"]), "medidas": len(medidas),
            "fidelidad_media": round(statistics.mean(medidas), 3) if medidas else None,
            "fidelidad_mediana": round(statistics.median(medidas), 3) if medidas else None,
            "por_tipo": por_tipo, "oraciones": len(frases),
            "veredictos": {str(v): frases.count(v) for v in (*VEREDICTOS, None) if frases.count(v)},
            "meta": 0.70, "cumple": bool(medidas) and statistics.mean(medidas) >= 0.70}


def fidelidad_s2(args) -> None:
    """OE3.I2: S2 answered by the assistant as deployed (local agent with tools and buscar_documentos), and the
    faithfulness of each answer as RAGAS defines it (share of the answer's statements supported by what it cites:
    passages and exact-core rows), graded by a local judge. Rule fixed before measuring (pendientes/26, 24/11/2026): the
    indicator is met if the mean over the answers that cite evidence is 0.70 or more; abstentions are reported apart.

    Since 26/11/2026 (review of the short paper) the statements are the answer's sentences and the judge labels each one
    (evaluation/fidelidad.py), and every row keeps its sentences and the evidence it cites, so ``rejuzgar-s2`` can grade
    the same answers with judges of other families and ``fidelidad-muestra`` can hand them to a human annotator."""
    from assistant.answer import build_answerer
    from assistant.config import load_assistant_config
    from evaluation.fidelidad import Juez, fidelidad, juzgar, oraciones, reintentar
    from knowledge.corpus.store import CorpusStore, connect, migrate

    conn = connect()
    migrate(conn)
    cfg = load_assistant_config()
    if args.modelo:                     # second generator (26/11/2026): same tools, guard and prompts
        cfg.generators.setdefault("local", {})["model"] = args.modelo
    cfg.orchestration.verificador = args.verificador           # stage B (27/11/2026); None = off
    cfg.orchestration.buscar_por_partes = args.por_partes       # stage D2 (27/11/2026)
    cfg.orchestration.guarda_valores = not args.sin_guarda_salida
    if args.lista_grafo:                                         # stage D3 (27/11/2026)
        cfg.retrieval.graph_list_weight = args.lista_grafo
    cfg.retrieval.entity_hop = args.salto_entidad                # stage D4 (27/11/2026)
    answerer = build_answerer(CorpusStore(conn), cfg)
    if answerer.agente is None:
        raise SystemExit("El asistente no tiene el agente (generador local con herramientas): revisa assistant.yaml")
    local = cfg.generators.get("local", {})
    base_url = local.get("base_url", "http://localhost:11434/v1")
    juez = Juez(base_url, args.juez)
    items = _particion(_s2_items(), args.particion)
    if args.n:
        items = items[: args.n]
    rag = _rag_convencional(base_url, local.get("model", "qwen3:8b")) if args.sistema == "rag" else None
    sufijo = (("_rag" if rag else "") + (f"_gen-{args.modelo.replace(':', '-')}" if args.modelo else "")
              + (f"_ver-{args.verificador.replace(':', '-').replace('.', '_')}" if args.verificador else "")
              + ("_por-partes" if args.por_partes else "")
              + (f"_grafo{args.lista_grafo:g}" if args.lista_grafo else "") + ("_salto" if args.salto_entidad else "")
              + (f"_{args.particion}" if args.particion != "todo" else ""))
    run = RUNS / f"{datetime.now():%Y-%m-%d_%H%M}_fidelidad_s2{sufijo}_{args.juez.replace(':', '-')}"
    run.mkdir(parents=True, exist_ok=True)
    filas = []
    with open(run / "respuestas.jsonl", "w", encoding="utf-8") as f:
        for it in items:
            extra = {}
            if rag:   # the baseline answers from its six passages; what it cites is its evidence
                rr = reintentar(lambda q=it["pregunta"]: rag.responder(q))
                texto, filas_grafo = rr.texto, []
                citadas = [(k, rr.pasajes[k - 1]) for k in rr.citados]
                evidencia = [{"ref": f"[{k}]", "doc_id": p.doc_id, "chunk_id": p.chunk_id, "texto": p.text}
                             for k, p in citadas]
                con_evidencia = bool(rr.citados)
            else:
                res = reintentar(lambda q=it["pregunta"]: answerer.answer(q))
                texto, filas_grafo = res.text, res.graph_rows
                evidencia = [{"ref": f"[{c.n}]", "doc_id": c.doc_id, "chunk_id": c.chunk_id, "texto": c.text}
                             for c in res.citations]
                evidencia += [{"ref": f"[G{i}]", "doc_id": None, "chunk_id": None,
                               "texto": json.dumps(r, ensure_ascii=False)} for i, r in enumerate(res.graph_rows, 1)]
                con_evidencia = res.evidence
                extra = {k: res.trace.get(k) for k in ("retiradas", "texto_sin_verificar", "evidencia_sin_verificar",
                                                       "corregido", "llamadas")}
                extra["busquedas"] = sum(1 for c in res.trace.get("llamadas") or [] if c["nombre"] == "buscar_documentos")
            frases = oraciones(texto) if con_evidencia and evidencia else []
            veredictos = juzgar(juez, frases, [f"{e['ref']} {e['texto']}" for e in evidencia]) if frases else []
            oro = sorted({e["doc_id"] for e in it.get("evidencias", [])})
            citados = sorted({e["doc_id"] for e in evidencia if e["doc_id"]})
            fila = {"qid": it["qid"], "tipo": it.get("tipo"), "evidencia": con_evidencia,
                    "citas": sum(1 for e in evidencia if e["doc_id"]), "filas_grafo": len(filas_grafo),
                    "docs_oro": oro, "docs_citados": citados, "oro_citados": len(set(oro) & set(citados)),
                    "oraciones": frases, "veredictos": veredictos, "fidelidad": fidelidad(veredictos),
                    "respuesta": texto, "evidencia_citada": evidencia, **(extra if not rag else {})}
            filas.append(fila)
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
            f.flush()
            print(f"{it['qid']} {it.get('tipo')!s:10} fid={fila['fidelidad']} oro={fila['oro_citados']}/{len(oro)} "
                  f"{veredictos} {texto[:60]!r}", flush=True)
    resumen = _resumen_fidelidad(filas, suite="textual.jsonl (S2)", sistema=args.sistema,
                                 generador=local.get("model", "qwen3:8b"), juez=juez.name,
                                 unidad="oraciones de la respuesta (evaluation/fidelidad.py)")
    (run / "metricas.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=1))
    print(f"corrida: {run}")


def repetibilidad_s2(args) -> None:
    """Determinism of the deployed agent (27/11/2026): each S2 question answered ``repeticiones`` times in a row with
    the same configuration, and whether the final text, the cited passages and the tool calls come out the same. The
    retrieval, the tools and the graph are deterministic, so any difference comes from the model's sampling. Run
    with the earlier setting (temperature 0.1, no seed) and with temperature 0 and a fixed seed."""
    from assistant.answer import build_answerer
    from assistant.config import load_assistant_config
    from evaluation.fidelidad import reintentar
    from knowledge.corpus.store import CorpusStore, connect, migrate

    conn = connect()
    migrate(conn)
    cfg = load_assistant_config()
    if args.modelo:
        cfg.generators.setdefault("local", {})["model"] = args.modelo
    cfg.generator.temperature = args.temperatura
    cfg.generator.seed = None if args.semilla < 0 else args.semilla
    answerer = build_answerer(CorpusStore(conn), cfg)
    if answerer.agente is None:
        raise SystemExit("El asistente no tiene el agente (generador local con herramientas): revisa assistant.yaml")
    modelo = cfg.generators.get("local", {}).get("model", "qwen3:8b")
    items = _particion(_s2_items(), args.particion)[: args.n or None]
    run = RUNS / (f"{datetime.now():%Y-%m-%d_%H%M}_repetibilidad_s2_{modelo.replace(':', '-')}_t{args.temperatura:g}"
                  f"_{'sin-semilla' if cfg.generator.seed is None else f'semilla{cfg.generator.seed}'}")
    run.mkdir(parents=True, exist_ok=True)
    filas = []
    with open(run / "por_pregunta.jsonl", "w", encoding="utf-8") as f:
        for it in items:
            vueltas = []
            for _ in range(args.repeticiones):
                res = reintentar(lambda q=it["pregunta"]: answerer.answer(q))
                vueltas.append({"texto": res.text, "citas": sorted(c.chunk_id for c in res.citations),
                                "llamadas": [(c["nombre"], json.dumps(c.get("argumentos"), sort_keys=True, ensure_ascii=False))
                                             for c in res.trace.get("llamadas") or []]})
            igual = lambda k, v=vueltas: all(x[k] == v[0][k] for x in v[1:])
            fila = {"qid": it["qid"], "tipo": it.get("tipo"), "texto_igual": igual("texto"), "citas_iguales": igual("citas"),
                    "llamadas_iguales": igual("llamadas"), "vueltas": vueltas}
            filas.append(fila)
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
            f.flush()
            print(f"{it['qid']} texto={fila['texto_igual']} citas={fila['citas_iguales']} "
                  f"llamadas={fila['llamadas_iguales']}", flush=True)
    n = len(filas)
    resumen = {"modelo": modelo, "temperatura": args.temperatura, "semilla": cfg.generator.seed,
               "repeticiones": args.repeticiones, "preguntas": n,
               "texto_igual": sum(x["texto_igual"] for x in filas), "citas_iguales": sum(x["citas_iguales"] for x in filas),
               "llamadas_iguales": sum(x["llamadas_iguales"] for x in filas)}
    (run / "metricas.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=1))
    print(f"corrida: {run}")


def _filas(nombre: str) -> list[dict]:
    return [json.loads(x) for x in (RUNS / nombre / "respuestas.jsonl").read_text(encoding="utf-8").splitlines()
            if x.strip()]


def rejuzgar_s2(args) -> None:
    """The same answers and evidence of a ``fidelidad-s2`` run, graded sentence by sentence by another judge (a model
    of another family, against self-preference of the generator's own family). Nothing is answered again."""
    from assistant.config import load_assistant_config
    from evaluation.fidelidad import Juez, fidelidad, juzgar

    fuente = _filas(args.corrida)
    if not any("oraciones" in x for x in fuente):
        raise SystemExit(f"{args.corrida} no guarda oraciones ni evidencia: córrela de nuevo con fidelidad-s2")
    local = load_assistant_config().generators.get("local", {})
    juez = Juez(local.get("base_url", "http://localhost:11434/v1"), args.juez)
    run = RUNS / f"{datetime.now():%Y-%m-%d_%H%M}_rejuicio_s2_{args.juez.replace(':', '-').replace('.', '_')}"
    run.mkdir(parents=True, exist_ok=True)
    filas = []
    with open(run / "respuestas.jsonl", "w", encoding="utf-8") as f:
        for x in fuente:
            ev = [f"{e['ref']} {e['texto']}" for e in x.get("evidencia_citada", [])]
            veredictos = juzgar(juez, x["oraciones"], ev) if x["oraciones"] else []
            fila = {k: x[k] for k in ("qid", "tipo", "evidencia", "citas", "docs_oro", "docs_citados", "oro_citados",
                                      "oraciones")}
            fila |= {"veredictos": veredictos, "fidelidad": fidelidad(veredictos)}
            filas.append(fila)
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
            f.flush()
            print(f"{x['qid']} fid={fila['fidelidad']} {veredictos}", flush=True)
    fuente_meta = json.loads((RUNS / args.corrida / "metricas.json").read_text(encoding="utf-8"))
    resumen = _resumen_fidelidad(filas, suite="textual.jsonl (S2)", corrida_fuente=args.corrida,
                                 sistema=fuente_meta.get("sistema"), generador=fuente_meta.get("generador"),
                                 juez=juez.name, unidad="oraciones de la respuesta (evaluation/fidelidad.py)")
    (run / "metricas.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=1))
    print(f"corrida: {run}")


FIDELIDAD_MUESTRA = SUITES / "fidelidad_s2_muestra_anotacion.xlsx"
VEREDICTO_COL = "Tu veredicto"


def _libro_anotacion(bloques: list[tuple[str, list[dict], list[tuple[str, str]]]], destino, extra: list[str] = ()) -> int:
    """Writes the faithfulness annotation workbook: a guide sheet and one row per sentence, blocks of the same answer
    with the same background and the cited evidence on their first row. ``bloques`` holds (question, evidence,
    [(hidden id, sentence)]). Returns the number of sentences."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.worksheet.datavalidation import DataValidation

    from evaluation.fidelidad import VEREDICTOS

    wb = Workbook()
    guia = wb.active
    guia.title = "Cómo anotar"
    for linea in [["Veredicto", "Cuándo"],
                  ["respaldada", "Lo que dice la oración está en la evidencia citada (aunque con otras palabras)."],
                  ["mezcla", ("Junta datos de pasajes distintos en algo que ninguno dice (p. ej., la dosis de un "
                              "producto con el cultivo de otro).")],
                  ["ausente", "Dice algo que no está en ningún pasaje ni fila citada."],
                  ["contradice", "La evidencia dice lo contrario."], [],
                  ["", "Juzga solo con la evidencia de la columna «Evidencia citada», no con lo que sabes del tema."],
                  ["", "Una oración que dice que no hay información suficiente es «respaldada» si la evidencia no trae el dato."],
                  ["", "Cada bloque con el mismo fondo es una respuesta; la evidencia está en su primera fila."],
                  *[["", t] for t in extra]]:
        guia.append(linea)
    guia.column_dimensions["A"].width, guia.column_dimensions["B"].width = 12, 100
    guia["A1"].font = guia["B1"].font = Font(bold=True)
    ws = wb.create_sheet("Anotar")
    ws.append(["N.°", "Pregunta", "Evidencia citada", "Oración", VEREDICTO_COL, "id"])
    for col, w in zip("ABCDEF", (6, 30, 80, 55, 14, 4)):
        ws.column_dimensions[col].width = w
    ws.column_dimensions["F"].hidden = True
    blanco = Font(bold=True, color="FFFFFF")
    for c in ws[1]:
        c.font, c.fill = blanco, PatternFill("solid", fgColor="2F5D50")
    fondos = [PatternFill("solid", fgColor="FFFFFF"), PatternFill("solid", fgColor="EEF4F1")]
    amarillo, ajuste = PatternFill("solid", fgColor="FFF6D5"), Alignment(wrap_text=True, vertical="top")
    borde = Border(top=Side(style="medium", color="2F5D50"))
    n = 0
    for g, (pregunta, evidencia, frases) in enumerate(bloques):
        ev = "\n\n".join(f"{e['ref']} {' '.join(e['texto'].split())[:1800]}" for e in evidencia)
        for i, (oid, s) in enumerate(frases, 1):
            n += 1
            ws.append([n, pregunta if i == 1 else "↑", ev if i == 1 else "↑ misma evidencia", s, None, oid])
            r = ws.max_row
            for c in ws[r]:
                c.alignment, c.fill = ajuste, fondos[g % 2]
                if i == 1:
                    c.border = borde
            ws.cell(r, 5).fill = amarillo
            ws.row_dimensions[r].height = min(409, 15 * (int(max(len(ev) / 95 if i == 1 else 1, len(s) / 60)) + 1))
    dv = DataValidation(type="list", formula1='"' + ",".join(VEREDICTOS) + '"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"E2:E{ws.max_row}")
    ws.freeze_panes = "D2"
    wb.active = 1
    wb.save(destino)
    return n


def fidelidad_muestra(args) -> None:
    """Excel for the human check of faithfulness: every multi-hop answer with evidence plus single-hop answers drawn
    with a fixed seed up to ``n`` answers; one row per sentence, the cited evidence beside the first sentence of each
    answer, the judges' labels hidden."""
    import random

    preguntas = {i["qid"]: i["pregunta"] for i in _s2_items()}
    filas = [x for x in _filas(args.corrida) if x.get("oraciones")]
    multi = [x for x in filas if x["tipo"] == "varios_saltos"]
    simples = [x for x in filas if x["tipo"] != "varios_saltos"]
    rng = random.Random(20261126)
    toma = multi + rng.sample(simples, max(0, min(len(simples), args.n - len(multi))))
    toma.sort(key=lambda x: x["qid"])

    bloques = [(preguntas.get(x["qid"], ""), x["evidencia_citada"],
                [(f"{x['qid']}:{i}", s) for i, s in enumerate(x["oraciones"], 1)]) for x in toma]
    n = _libro_anotacion(bloques, FIDELIDAD_MUESTRA)
    meta = {"corrida": args.corrida, "respuestas": len(toma), "oraciones": n,
            "varios_saltos": sum(x["tipo"] == "varios_saltos" for x in toma), "semilla": 20261126}
    (SUITES / "fidelidad_s2_muestra.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False), f"\n{FIDELIDAD_MUESTRA}")


def _anotacion(archivo) -> dict[str, str]:
    from openpyxl import load_workbook

    from evaluation.fidelidad import VEREDICTOS

    ws = load_workbook(archivo, read_only=True)["Anotar"]
    filas = ws.iter_rows(values_only=True)
    cab = list(next(filas))
    vi, ii = cab.index(VEREDICTO_COL), cab.index("id")
    out = {}
    for f in filas:
        v = str(f[vi] or "").strip().lower()
        if v in VEREDICTOS and f[ii]:
            out[f[ii]] = v
    return out


def fidelidad_acuerdo(args) -> None:
    """Agreement among the judges and with the human annotation, and the error analysis of S2 (review of 26/11/2026).

    For every judge run (the ``fidelidad-s2`` run and its ``rejuzgar-s2`` runs over the same answers): mean faithfulness
    overall and by question type; Cohen's kappa against the human labels (supported or not, and the four labels) on the
    annotated sentences; kappa between each pair of judges on all sentences; the labels of the unsupported sentences of
    multi-hop answers; and faithfulness by how many of the two gold documents the answer cites."""
    import itertools
    import statistics

    from evaluation.fidelidad import cohen_kappa

    corridas = [args.corrida, *args.jueces]
    por = {c: {x["qid"]: x for x in _filas(c)} for c in corridas}
    nombre = {c: json.loads((RUNS / c / "metricas.json").read_text(encoding="utf-8"))["juez"] for c in corridas}
    humano = _anotacion(args.anotacion) if args.anotacion else {}

    def etiquetas(c):
        return {f"{q}:{i}": v for q, x in por[c].items() for i, v in enumerate(x.get("veredictos") or [], 1)}

    et = {c: etiquetas(c) for c in corridas}
    media = lambda v: round(statistics.mean(v), 3) if v else None
    out = {"corrida": args.corrida, "anotacion": str(args.anotacion or ""), "oraciones_anotadas": len(humano),
           "jueces": {}, "entre_jueces": {}, "humano": {}}
    for c in corridas:
        fid = [x["fidelidad"] for x in por[c].values() if x["fidelidad"] is not None]
        j = {"corrida": c, "media": media(fid),
             "por_tipo": {t: media([x["fidelidad"] for x in por[c].values() if x["tipo"] == t and x["fidelidad"] is not None])
                          for t in ("un_salto", "varios_saltos")}}
        comunes = [k for k in humano if et[c].get(k)]
        if comunes:
            h, m = [humano[k] for k in comunes], [et[c][k] for k in comunes]
            j |= {"n_humano": len(comunes),
                  "kappa_respaldada_si_no": cohen_kappa([v == "respaldada" for v in h], [v == "respaldada" for v in m]),
                  "kappa_4_etiquetas": cohen_kappa(h, m),
                  "acuerdo_exacto": round(sum(a == b for a, b in zip(h, m)) / len(h), 3)}
            # faithfulness of the annotated answers by this judge and by the person, answer by answer
            qids = sorted({k.split(":")[0] for k in comunes})
            fh = [statistics.mean(humano[k] == "respaldada" for k in comunes if k.startswith(q + ":")) for q in qids]
            fm = [statistics.mean(et[c][k] == "respaldada" for k in comunes if k.startswith(q + ":")) for q in qids]
            j |= {"fidelidad_muestra_juez": media(fm), "fidelidad_muestra_humano": media(fh),
                  "error_absoluto_medio": round(statistics.mean(abs(a - b) for a, b in zip(fh, fm)), 3)}
        out["jueces"][nombre[c]] = j
    for a, b in itertools.combinations(corridas, 2):
        k = [x for x in et[a] if et[b].get(x) and et[a][x]]
        out["entre_jueces"][f"{nombre[a]} | {nombre[b]}"] = {
            "oraciones": len(k), "kappa_respaldada_si_no": cohen_kappa([et[a][x] == "respaldada" for x in k],
                                                                      [et[b][x] == "respaldada" for x in k]),
            "kappa_4_etiquetas": cohen_kappa([et[a][x] for x in k], [et[b][x] for x in k])}
    # error analysis of multi-hop answers: labels of the sentences that are not supported, per judge and by the person
    for c in corridas:
        no = [v for q, x in por[c].items() if x["tipo"] == "varios_saltos" for v in (x.get("veredictos") or [])
              if v != "respaldada"]
        out["jueces"][nombre[c]]["varios_saltos_no_respaldadas"] = {v: no.count(v) for v in sorted(set(no), key=str)}
        cob = {}
        for n_oro in (0, 1, 2):
            v = [x["fidelidad"] for x in por[c].values() if x["tipo"] == "varios_saltos" and x["fidelidad"] is not None
                 and x["oro_citados"] == n_oro]
            cob[f"cita_{n_oro}_de_2_docs_oro"] = {"respuestas": len(v), "fidelidad": media(v)}
        out["jueces"][nombre[c]]["varios_saltos_por_cobertura"] = cob
    hv = [v for k, v in humano.items() if por[args.corrida].get(k.split(":")[0], {}).get("tipo") == "varios_saltos"]
    out["humano"]["varios_saltos"] = {v: hv.count(v) for v in sorted(set(hv))}
    run = RUNS / f"{datetime.now():%Y-%m-%d_%H%M}_acuerdo_fidelidad"
    run.mkdir(parents=True, exist_ok=True)
    (run / "metricas.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"corrida: {run}")


FIDELIDAD_VERIFICACION = SUITES / "fidelidad_s2_verificacion_anotacion.xlsx"
FIDELIDAD_VERIFICACION_META = SUITES / "fidelidad_s2_verificacion_muestra.json"
SEMILLA_VERIFICACION = 20261127
_CITA = re.compile(r"\[(\d+)\]")


def _antes_despues(x: dict) -> tuple[list[str], list[dict], list[str]]:
    """An answer of a run with the sentence check: its sentences and evidence before the check, and the kept sentences.
    An answer the check did not change has no ``texto_sin_verificar``, so before and after are the same."""
    from evaluation.fidelidad import oraciones

    if x.get("texto_sin_verificar"):
        ev = x.get("evidencia_sin_verificar") or []
        return (oraciones(x["texto_sin_verificar"]) if ev else []), ev, list(x.get("oraciones") or [])
    return list(x.get("oraciones") or []), x.get("evidencia_citada") or [], list(x.get("oraciones") or [])


def _textos(ev: list[dict]) -> dict[str, str]:
    return {e["ref"]: " ".join(e["texto"].split()) for e in ev}


def fidelidad_muestra_verificacion(args) -> None:
    """Excel for the human check of the sentence-level verification (rule in pendientes/26, stage B, 27/11/2026).

    Same 30 questions as the annotation of 26/11. For each run with the check, every sentence of each answer before
    the check, plus a kept sentence the split did not find there. A sentence the person already labelled is reused only
    when it belongs to the same question and every passage it cites has the same text (with no citation, the whole
    evidence must match); the rest go to the sheet. Answer blocks of all runs are shuffled with a fixed seed and carry an
    opaque id, so the sheet shows neither the generator nor which sentences the verifier kept."""
    import hashlib
    import random

    preguntas = {i["qid"]: i["pregunta"] for i in _s2_items()}
    previas = _anotacion(FIDELIDAD_MUESTRA)
    base = {x["qid"]: x for x in _filas(args.base)}
    reusable = {}
    for k, v in previas.items():
        q, i = k.split(":")
        x = base[q]
        reusable[(q, x["oraciones"][int(i) - 1])] = (v, _textos(x["evidencia_citada"]))
    qids = sorted({k.split(":")[0] for k in previas})
    oraciones_meta, bloques = {}, []
    for c in args.corridas:
        filas = {x["qid"]: x for x in _filas(c)}
        for q in qids:
            x = filas.get(q)
            if not x:
                continue
            antes, ev, despues = _antes_despues(x)
            tex, nuevas = _textos(ev), []
            for s in dict.fromkeys(antes + [d for d in despues if d not in antes]):
                r = reusable.get((q, s))
                refs = {f"[{n}]" for n in _CITA.findall(s)}
                igual = bool(r) and (all(f in tex and tex[f] == r[1].get(f) for f in refs) if refs else tex == r[1])
                clave = f"{c}|{q}|{hashlib.sha1(s.encode('utf-8')).hexdigest()[:12]}"
                oraciones_meta[clave] = {"corrida": c, "qid": q, "tipo": x["tipo"], "oracion": s, "antes": s in antes,
                                         "despues": s in despues, "reutilizada": r[0] if igual else None}
                if not igual:
                    nuevas.append((clave, s))
            if nuevas:
                bloques.append((q, ev, nuevas))
    random.Random(SEMILLA_VERIFICACION).shuffle(bloques)
    ids, hoja = {}, []
    for q, ev, nuevas in bloques:
        filas_hoja = []
        for clave, s in nuevas:
            oid = f"v{len(ids) + 1:03d}"
            ids[oid] = clave
            filas_hoja.append((oid, s))
        hoja.append((preguntas.get(q, ""), ev, filas_hoja))
    if FIDELIDAD_VERIFICACION.exists() and not args.forzar:
        raise SystemExit(f"{FIDELIDAD_VERIFICACION} ya existe (puede tener anotaciones); usa --forzar para rehacerlo")
    n = _libro_anotacion(hoja, FIDELIDAD_VERIFICACION, extra=[
        "Algunas respuestas aparecen incompletas: solo se piden las oraciones que no anotaste antes.",
        "La misma pregunta puede aparecer más de una vez, con respuestas distintas; anota cada una por separado."])
    meta = {"base": args.base, "corridas": args.corridas, "semilla": SEMILLA_VERIFICACION, "preguntas": len(qids),
            "oraciones": len(oraciones_meta), "a_anotar": n,
            "reutilizadas": sum(o["reutilizada"] is not None for o in oraciones_meta.values()),
            "por_corrida": {c: {"a_anotar": sum(1 for k in ids.values() if k.startswith(c + "|")),
                                "reutilizadas": sum(1 for o in oraciones_meta.values()
                                                    if o["corrida"] == c and o["reutilizada"] is not None)}
                            for c in args.corridas},
            "ids": ids, "detalle": oraciones_meta}
    FIDELIDAD_VERIFICACION_META.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in meta.items() if k not in ("ids", "detalle")}, ensure_ascii=False, indent=1))
    print(FIDELIDAD_VERIFICACION)


def _fuente_final(corrida: str) -> str:
    """The run with the sentence check behind a judge run: rejuzgar-s2 and sin-verificar runs name their source."""
    vistas = set()
    while corrida not in vistas:
        vistas.add(corrida)
        meta = json.loads((RUNS / corrida / "metricas.json").read_text(encoding="utf-8"))
        if not meta.get("corrida_fuente"):
            return corrida
        corrida = meta["corrida_fuente"]
    return corrida


def fidelidad_acuerdo_verificacion(args) -> None:
    """The sentence-level check measured with the person (rule in pendientes/26, stage B): per run, faithfulness of
    the annotated answers before and after the check (share of supported sentences per answer), answers that keep text,
    the paired comparison on answers with text in both (Wilcoxon), the verifier's keep/remove decision against the
    person (Cohen's kappa), and each judge against the person on the same sentences."""
    import statistics

    from scipy.stats import wilcoxon

    from evaluation.fidelidad import cohen_kappa

    meta = json.loads(FIDELIDAD_VERIFICACION_META.read_text(encoding="utf-8"))
    nuevas = _anotacion(args.anotacion or FIDELIDAD_VERIFICACION)
    etiqueta = {clave: nuevas[oid] for oid, clave in meta["ids"].items() if oid in nuevas}
    etiqueta |= {k: o["reutilizada"] for k, o in meta["detalle"].items() if o["reutilizada"]}
    faltan = [k for k in meta["detalle"] if k not in etiqueta]
    media = lambda v: round(statistics.mean(v), 3) if v else None
    out = {"anotacion": str(args.anotacion or FIDELIDAD_VERIFICACION), "anotadas_ahora": len(nuevas),
           "reutilizadas": sum(o["reutilizada"] is not None for o in meta["detalle"].values()),
           "sin_etiqueta": len(faltan), "corridas": {}}
    por_texto = {(o["corrida"], o["qid"], o["oracion"]): k for k, o in meta["detalle"].items()}
    jueces = {}
    for d in sorted(RUNS.iterdir()):
        if (d / "respuestas.jsonl").exists() and (d / "metricas.json").exists():
            fuente = _fuente_final(d.name)
            juez = json.loads((d / "metricas.json").read_text(encoding="utf-8")).get("juez")
            if fuente in meta["corridas"] and juez:
                jueces.setdefault(fuente, []).append((d.name, juez))
    for c in meta["corridas"]:
        por_q = {}
        for k, o in meta["detalle"].items():
            if o["corrida"] == c:
                por_q.setdefault(o["qid"], []).append((k, o))
        filas, pares, sop, quedo = [], [], [], []
        for q, os_ in sorted(por_q.items()):
            a = [etiqueta[k] == "respaldada" for k, o in os_ if o["antes"] and k in etiqueta]
            d = [etiqueta[k] == "respaldada" for k, o in os_ if o["despues"] and k in etiqueta]
            fa, fd = (statistics.mean(a) if a else None), (statistics.mean(d) if d else None)
            filas.append({"qid": q, "tipo": os_[0][1]["tipo"], "antes": fa, "despues": fd})
            if fa is not None and fd is not None:
                pares.append((fa, fd))
            for k, o in os_:
                if o["antes"] and k in etiqueta:
                    sop.append(etiqueta[k] == "respaldada")
                    quedo.append(o["despues"])
        dif = [b - a for a, b in pares]
        try:
            p = round(float(wilcoxon([b for _, b in pares], [a for a, _ in pares]).pvalue), 4) if any(dif) else 1.0
        except ValueError:
            p = None
        n_a = sum(f["antes"] is not None for f in filas)
        n_d = sum(f["despues"] is not None for f in filas)
        fa_all = media([f["antes"] for f in filas if f["antes"] is not None])
        fd_all = media([f["despues"] for f in filas if f["despues"] is not None])
        ganancia = round(fd_all - fa_all, 3) if fa_all is not None and fd_all is not None else None
        perdida = round((n_a - n_d) / n_a, 3) if n_a else None
        r = {"respuestas_con_texto_antes": n_a, "respuestas_con_texto_despues": n_d,
             "fidelidad_persona_antes": fa_all, "fidelidad_persona_despues": fd_all,
             "por_tipo": {t: {"antes": media([f["antes"] for f in filas if f["tipo"] == t and f["antes"] is not None]),
                              "despues": media([f["despues"] for f in filas if f["tipo"] == t and f["despues"] is not None])}
                          for t in ("un_salto", "varios_saltos")},
             "pareadas": {"n": len(pares), "antes": media([a for a, _ in pares]), "despues": media([b for _, b in pares]),
                          "sube": sum(x > 0 for x in dif), "baja": sum(x < 0 for x in dif), "wilcoxon_p": p},
             # pre-registered rule: better if faithfulness rises by more than the share of answers lost
             "regla": {"ganancia_fidelidad": ganancia, "perdida_cobertura": perdida,
                       "mejora": ganancia is not None and perdida is not None and ganancia > 0 and ganancia > perdida},
             "verificador_frente_a_persona": {
                 "oraciones": len(sop), "kappa_conservar_frente_a_respaldada": cohen_kappa(sop, quedo),
                 "retiradas": sum(not k for k in quedo),
                 "retiradas_que_la_persona_no_respaldaba": sum((not k) and (not s) for s, k in zip(sop, quedo)),
                 "no_respaldadas_por_la_persona": sum(not s for s in sop),
                 "conservadas_que_la_persona_no_respaldaba": sum(k and (not s) for s, k in zip(sop, quedo))},
             "jueces_frente_a_persona": {}}
        for nombre, juez in jueces.get(c, []):
            h, m = [], []
            for x in _filas(nombre):
                for s, v in zip(x.get("oraciones") or [], x.get("veredictos") or []):
                    k = por_texto.get((c, x["qid"], s))
                    if k in etiqueta and v:
                        h.append(etiqueta[k] == "respaldada")
                        m.append(v == "respaldada")
            if h:
                r["jueces_frente_a_persona"][nombre] = {"juez": juez, "oraciones": len(h), "kappa": cohen_kappa(h, m)}
        r["por_respuesta"] = filas
        out["corridas"][c] = r
    run = RUNS / f"{datetime.now():%Y-%m-%d_%H%M}_acuerdo_verificacion"
    run.mkdir(parents=True, exist_ok=True)
    (run / "metricas.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({c: {k: v for k, v in r.items() if k != "por_respuesta"} for c, r in out["corridas"].items()}
                     | {"sin_etiqueta": len(faltan)}, ensure_ascii=False, indent=1))
    print(f"corrida: {run}")


def juicios_rejuez(args) -> None:
    """The 180 relevance judgments annotated by hand, graded again by a judge of another family: Cohen's kappa of
    that judge against the person and against the Qwen judge, with the prompt the Qwen judge used."""
    from openpyxl import load_workbook

    from assistant.config import load_assistant_config
    from evaluation.fidelidad import Juez, cohen_kappa
    from evaluation.judgments import GRADE_COL, JUDGE, Judgments
    from evaluation.textual_suite import _json
    from knowledge.corpus.store import connect

    store = Judgments(JUICIOS)
    by_id = {f"{r['qid']}:{r['hash']}": r for r in store.rows}
    preguntas = {i["qid"]: i["pregunta"] for i in _s2_items()}
    titulos = dict(connect().execute("SELECT doc_id, titulo FROM documentos").fetchall())
    local = load_assistant_config().generators.get("local", {})
    juez = Juez(local.get("base_url", "http://localhost:11434/v1"), args.juez, num_ctx=4096)
    ws = load_workbook(args.archivo, read_only=True)["Anotar"]
    filas = ws.iter_rows(values_only=True)
    cab = list(next(filas))
    gi, ii = cab.index(GRADE_COL), cab.index("id")
    ella, qwen, otro, salida = [], [], [], []
    for f in filas:
        g = str(f[gi]).strip().removesuffix(".0") if f[gi] is not None else ""
        r = by_id.get(f[ii])
        if g not in ("0", "1", "2") or r is None:
            continue
        d = _json(juez.chat(JUDGE, f"Pregunta: {preguntas[r['qid']]}\n\nFragmento de «{titulos.get(r['doc_id'], r['doc_id'])}», "
                                   f"p. {', '.join(map(str, r['paginas']))}:\n{r['texto'][:2500]}"))
        o = int(d["grado"]) if str(d.get("grado")) in ("0", "1", "2") else 0
        ella.append(int(g))
        qwen.append(r["grado"])
        otro.append(o)
        salida.append({"id": f[ii], "humano": int(g), "qwen": r["grado"], "otro": o})
    si = lambda v: [x >= 1 for x in v]
    res = {"fecha": datetime.now().date().isoformat(), "juez": juez.name, "n": len(ella),
           "kappa_relevante_si_no_vs_humano": cohen_kappa(si(ella), si(otro)),
           "kappa_0_1_2_vs_humano": cohen_kappa(ella, otro),
           "kappa_relevante_si_no_qwen_vs_humano": cohen_kappa(si(ella), si(qwen)),
           "kappa_relevante_si_no_vs_qwen": cohen_kappa(si(qwen), si(otro)),
           "kappa_0_1_2_vs_qwen": cohen_kappa(qwen, otro)}
    run = RUNS / f"{datetime.now():%Y-%m-%d_%H%M}_juicios_rejuez_{args.juez.replace(':', '-').replace('.', '_')}"
    run.mkdir(parents=True, exist_ok=True)
    (run / "metricas.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    (run / "juicios.jsonl").write_text("\n".join(json.dumps(s) for s in salida) + "\n", encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"corrida: {run}")


def analisis_u1(args) -> None:
    """Why the hybrid list has a lower useful@1 than the dense list (review of 26/11/2026): per question, whether the
    first passage of each list answers it (grade 2), and for the hybrid's first passage, its rank in the lexical and
    the dense lists (where reciprocal rank fusion took it from) and the rank the hybrid gives to the dense first."""
    from collections import Counter

    from evaluation.judgments import Judgments, fragments
    from knowledge.corpus.store import connect, migrate

    conn = connect()
    migrate(conn)
    store = Judgments(JUICIOS)
    r = _retrievers(conn, ["idf"], args.firma)["idf"]
    grado = lambda q, c, f: (store.grade(q, f[c]["doc_id"], f[c]["paginas"], f[c]["texto"]) or 0) if c in f else 0
    filas, casos = [], Counter()
    for it in _s2_items():
        q = it["pregunta"]
        lex = r.lexical(q)
        den = [c for c, _ in r.dense(q)]
        hib = [p.chunk_id for p in r.retrieve(q)]
        frs = fragments(conn, r.signature, list({*lex[:1], *den[:1], *hib[:10]}))
        h1, d1 = (hib[0] if hib else None), (den[0] if den else None)
        gh, gd = grado(it["qid"], h1, frs), grado(it["qid"], d1, frs)
        caso = ("ambos" if gh == 2 and gd == 2 else "solo_denso" if gd == 2 else "solo_hibrido" if gh == 2 else "ninguno")
        casos[caso] += 1
        fila = {"qid": it["qid"], "tipo": it["tipo"], "caso": caso, "grado_h1": gh, "grado_d1": gd,
                "h1_rango_lexico": lex.index(h1) + 1 if h1 in lex else None,
                "h1_rango_denso": den.index(h1) + 1 if h1 in den else None,
                "d1_rango_hibrido": hib.index(d1) + 1 if d1 in hib else None,
                "d1_rango_lexico": lex.index(d1) + 1 if d1 in lex else None}
        filas.append(fila)
        print(json.dumps(fila), flush=True)
    perdidas = [f for f in filas if f["caso"] == "solo_denso"]
    origen = Counter("solo_lexico" if f["h1_rango_denso"] is None else "solo_denso" if f["h1_rango_lexico"] is None
                     else "ambos" for f in perdidas)
    res = {"firma": r.signature, "preguntas": len(filas), "casos": dict(casos),
           "util1_hibrido": round(sum(f["grado_h1"] == 2 for f in filas) / len(filas), 3),
           "util1_denso": round(sum(f["grado_d1"] == 2 for f in filas) / len(filas), 3),
           "solo_denso_origen_del_primero_hibrido": dict(origen),
           "solo_denso_rango_hibrido_del_primero_denso": sorted(f["d1_rango_hibrido"] or 99 for f in perdidas),
           "solo_denso_rango_lexico_del_primero_denso": sorted(f["d1_rango_lexico"] or 99 for f in perdidas),
           "solo_denso_por_tipo": dict(Counter(f["tipo"] for f in perdidas))}
    run = RUNS / f"{datetime.now():%Y-%m-%d_%H%M}_analisis_u1"
    run.mkdir(parents=True, exist_ok=True)
    (run / "metricas.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    (run / "por_pregunta.jsonl").write_text("\n".join(json.dumps(f) for f in filas) + "\n", encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"corrida: {run}")


def sin_verificar(args) -> None:
    """From a ``fidelidad-s2`` run with the sentence check (stage B), the same answers before the check (stage A): the
    original text and what it cited, re-split into sentences, ready for ``rejuzgar-s2``. Both versions come from one
    generation, so the comparison isolates the check (27/11/2026)."""
    from evaluation.fidelidad import oraciones

    fuente = _filas(args.corrida)
    meta = json.loads((RUNS / args.corrida / "metricas.json").read_text(encoding="utf-8"))
    run = RUNS / f"{datetime.now():%Y-%m-%d_%H%M}_sin-verificar_{args.corrida[16:]}"
    run.mkdir(parents=True, exist_ok=True)
    filas, cambiadas = [], 0
    for x in fuente:
        y = dict(x)
        if x.get("texto_sin_verificar"):
            cambiadas += 1
            ev = x.get("evidencia_sin_verificar") or []
            citados = sorted({e["doc_id"] for e in ev if e["doc_id"]})
            y |= {"respuesta": x["texto_sin_verificar"], "evidencia_citada": ev, "evidencia": bool(ev),
                  "citas": sum(1 for e in ev if e["doc_id"]), "docs_citados": citados,
                  "oro_citados": len(set(x.get("docs_oro", [])) & set(citados)),
                  "oraciones": oraciones(x["texto_sin_verificar"]) if ev else []}
        y |= {"veredictos": [], "fidelidad": None}
        for k in ("retiradas", "texto_sin_verificar", "evidencia_sin_verificar"):
            y.pop(k, None)
        filas.append(y)
    (run / "respuestas.jsonl").write_text("\n".join(json.dumps(f, ensure_ascii=False) for f in filas) + "\n",
                                          encoding="utf-8")
    resumen = {"suite": meta.get("suite"), "sistema": meta.get("sistema"), "generador": meta.get("generador"),
               "juez": None, "corrida_fuente": args.corrida, "respuestas_cambiadas_por_la_verificacion": cambiadas,
               "nota": "respuestas originales antes de la verificación por oraciones; juzgar con rejuzgar-s2"}
    (run / "metricas.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False))
    print(f"corrida: {run}")


def cobertura_documentos(args) -> None:
    """Stage D metric (27/11/2026): for each S2 question, how many of its reference documents (the documents of its
    evidence spans; two for multi-hop) are among the passages the generator reads (top ``k``) with the deployed
    retriever, optionally with a cap of fragments per document. Reported for multi-hop and single-hop, on a split."""
    import statistics
    from collections import Counter

    from assistant.answer import build_answerer
    from assistant.config import load_assistant_config
    from knowledge.corpus.store import CorpusStore, connect, migrate

    conn = connect()
    migrate(conn)
    cfg = load_assistant_config()
    if args.tope is not None:
        cfg.retrieval.max_per_document = args.tope or None
    if args.lista_grafo is not None:
        cfg.retrieval.graph_list_weight = args.lista_grafo or None
    cfg.retrieval.entity_hop = args.salto_entidad
    r = build_answerer(CorpusStore(conn), cfg, "extractive").retriever
    r.top_k = args.k
    items = _particion(_s2_items(), args.particion)
    filas, por = [], {}
    for it in items:
        oro = {e["doc_id"] for e in it["evidencias"]}
        top = r.retrieve(it["pregunta"])
        docs = [p.doc_id for p in top]
        n = len(oro & set(docs))
        filas.append({"qid": it["qid"], "tipo": it["tipo"], "docs_oro": sorted(oro), "en_top": n,
                      "docs_distintos": len(set(docs))})
        por.setdefault(it["tipo"], []).append((n, len(oro), len(set(docs))))
    res = {"particion": args.particion, "k": args.k, "tope_por_documento": r.max_per_document,
           "lista_grafo": r.graph_list_weight, "salto_entidad": r.entity_hop, "firma": r.signature,
           "mmr": r.mmr_lambda, "preguntas": len(filas)}
    for t, v in por.items():
        res[t] = {"preguntas": len(v), "todos_los_docs_oro": sum(n == m for n, m, _ in v),
                  "al_menos_uno": sum(n >= 1 for n, _, _ in v), "ninguno": sum(n == 0 for n, _, _ in v),
                  "docs_distintos_media": round(statistics.mean(d for _, _, d in v), 2),
                  "distribucion": dict(Counter(n for n, _, _ in v))}
    tag = (f"_tope{r.max_per_document}" if r.max_per_document else "") + \
        (f"_grafo{r.graph_list_weight:g}" if r.graph_list_weight else "") + ("_salto" if r.entity_hop else "")
    run = RUNS / f"{datetime.now():%Y-%m-%d_%H%M}_cobertura_documentos_{args.particion}{tag}"
    run.mkdir(parents=True, exist_ok=True)
    (run / "metricas.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    (run / "por_pregunta.jsonl").write_text("\n".join(json.dumps(f, ensure_ascii=False) for f in filas) + "\n",
                                            encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"corrida: {run}")


def comparar(args) -> None:
    """Paired comparisons for the short paper (rules in pendientes/26, 24/11/2026). S1: exact answers of the full system
    against memory, the no-guard ablation and conventional RAG (exact McNemar). S2: faithfulness of the full system against
    conventional RAG over the questions both answered with evidence (Wilcoxon)."""
    from evaluation.comparacion import mcnemar_exacta, wilcoxon

    def filas(nombre):
        return {json.loads(x)["qid"]: json.loads(x) for x in (RUNS / nombre / "respuestas.jsonl").read_text(
            encoding="utf-8").splitlines() if x.strip()}

    base = filas(args.s1)
    out = {"s1": {"sistema": args.s1}, "s2": {}}
    for nombre in args.s1_contra:
        otro = filas(nombre)
        q = sorted(set(base) & set(otro))
        a, b = [base[k]["exacta"] for k in q], [otro[k]["exacta"] for k in q]
        out["s1"][nombre] = {"preguntas": len(q), "exactas_sistema": sum(a), "exactas_otro": sum(b), **mcnemar_exacta(a, b)}
    if args.s2 and args.s2_contra:
        x, y = filas(args.s2), filas(args.s2_contra)
        q = sorted(k for k in set(x) & set(y) if x[k]["fidelidad"] is not None and y[k]["fidelidad"] is not None)
        fx, fy = [x[k]["fidelidad"] for k in q], [y[k]["fidelidad"] for k in q]
        media = lambda v: round(sum(v) / len(v), 3) if v else None
        todas = lambda f: [r["fidelidad"] for r in f.values() if r["fidelidad"] is not None]
        out["s2"] = {"sistema": args.s2, "contra": args.s2_contra, "ambos_con_evidencia": len(q),
                     "media_sistema_pareada": media(fx), "media_otro_pareada": media(fy),
                     "media_sistema": media(todas(x)), "media_otro": media(todas(y)),
                     "respondidas_sistema": len(todas(x)), "respondidas_otro": len(todas(y)), **wilcoxon(fx, fy),
                     # coverage (27/11/2026): answered with evidence or not, per question, exact McNemar
                     "cobertura": mcnemar_exacta([bool(x[k]["evidencia"]) for k in sorted(set(x) & set(y))],
                                                 [bool(y[k]["evidencia"]) for k in sorted(set(x) & set(y))])}
    run = RUNS / f"{datetime.now():%Y-%m-%d_%H%M}_comparacion"
    run.mkdir(parents=True, exist_ok=True)
    (run / "metricas.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"corrida: {run}")


def validar_s3(args) -> None:
    """S3 (rule in pendientes/26, 24/11/2026): the exact core validates the 30 programs; a seeded violation is detected
    when a finding has its code, block and product. Recall over seeded, precision over non-INFO findings (a finding is
    correct if it matches a seeded or a recorded collateral violation), and programs flagged as non-compliant."""
    from datetime import date

    from domain.findings import Severity
    from domain.validation.models import Application, Block, Program
    from domain.validation.program import validate_program
    from interfaces.api.sources import graph_sources

    casos = [json.loads(x) for x in (SUITES / "programas.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    run = RUNS / f"{datetime.now():%Y-%m-%d_%H%M}_validador_s3"
    run.mkdir(parents=True, exist_ok=True)
    clave = lambda d: (d.get("code"), d.get("block"), d.get("product_id"))
    filas, sembradas, detectadas, hallazgos, correctos, marcados = [], 0, 0, 0, 0, 0
    gen = graph_sources()
    src = next(gen)
    try:
        for c in casos:
            pr = c["programa"]
            prog = Program(pr["crop"], tuple(Block(b["key"], date.fromisoformat(b["harvest_on"]), tuple(b["markets"]))
                                             for b in pr["blocks"]),
                           tuple(Application(a["block"], a["product_id"], date.fromisoformat(a["applied_on"]), a.get("pest"))
                                 for a in pr["applications"]))
            rep_ = validate_program(prog, src.registry, src.limits, src.moa)
            reales = [f for f in rep_.findings if f.severity != Severity.INFO]
            claves = {(f.code, f.block, f.product_id) for f in reales}
            esperadas = {clave(x) for x in c["sembradas"]}
            validas = esperadas | {clave(x) for x in c.get("colaterales", [])}
            det = len(esperadas & claves)
            sembradas, detectadas = sembradas + len(esperadas), detectadas + det
            hallazgos += len(claves)
            correctos += len(claves & validas)
            marcados += bool(reales)
            filas.append({"pid": c["pid"], "sembradas": sorted(map(list, esperadas)), "detectadas": det,
                          "hallazgos": sorted(map(list, claves)), "no_conforme": bool(reales)})
            print(f"{c['pid']} sembradas={len(esperadas)} detectadas={det} hallazgos={len(claves)}", flush=True)
    finally:
        gen.close()
    resumen = {"programas": len(casos), "sembradas": sembradas, "detectadas": detectadas,
               "exhaustividad": round(detectadas / sembradas, 3) if sembradas else None,
               "hallazgos": hallazgos, "precision": round(correctos / hallazgos, 3) if hallazgos else None,
               "programas_no_conformes": marcados}
    (run / "metricas.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    (run / "por_programa.jsonl").write_text("\n".join(json.dumps(f, ensure_ascii=False) for f in filas) + "\n",
                                            encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False))
    print(f"corrida: {run}")


REALES = SUITES / "programas_reales.json"
REALES_REFERENCIA = SUITES / "programas_reales_referencia.xlsx"
REF_COLS = ("¿Registrado para el cultivo?", "Carencia (días)", "LMR UE", "Tolerancia EE. UU.")


def _resolver_reales():
    from interfaces.api.sources import graph_sources
    from knowledge.normalization.ingredients import Aliases, spanish_names
    from knowledge.programs.resolver import Resolvedor

    gen = graph_sources()
    src = next(gen)
    aliases = Aliases.load()
    return gen, src, Resolvedor(src.limits.graph, src.registry, aliases, spanish_names(aliases))


def validar_reales(args) -> None:
    """S3, real programs (review of 26/11/2026): resolution of each row (product by trade name or ingredients, date,
    pest) and the validator's findings, per row and per program. Also writes the sheet for the reference set by hand."""
    from collections import Counter
    from datetime import date

    from domain.findings import Severity
    from domain.validation.models import Application, Block, Program
    from domain.validation.program import validate_program

    datos = json.loads(REALES.read_text(encoding="utf-8"))
    gen, src, res = _resolver_reales()
    run = RUNS / f"{datetime.now():%Y-%m-%d_%H%M}_validador_reales"
    run.mkdir(parents=True, exist_ok=True)
    filas, programas, items = [], [], {}
    try:
        for prog in datos["programas"]:
            rs = [res.resolver({**prog, "plaga": prog.get("plaga_texto")}, n, f) for n, f in enumerate(prog["filas"], 1)]
            apps = [r for r in rs if r.tipo == "plaguicida"]
            program = Program(prog["cultivo"], (Block("L1", date.fromisoformat(prog["cosecha_evaluacion"]),
                                                      tuple(prog["mercados"])),),
                              tuple(Application("L1", r.producto, r.fecha, r.plaga) for r in apps))
            hallazgos = [f for f in validate_program(program, src.registry, src.limits, src.moa).findings
                         if f.severity is not Severity.INFO]
            for r, crudo in zip(rs, prog["filas"]):
                propios = [f for f in hallazgos if r.producto and f.product_id == r.producto]
                fila = {"pid": r.pid, "n": r.n, "texto": r.texto, "tipo": r.tipo, "via": r.via, "producto": r.producto,
                        "nombre_producto": r.nombre_producto, "ingredientes": list(r.ingredientes),
                        "candidatos": r.candidatos, "discrepancia": r.discrepancia,
                        "fecha": r.fecha.isoformat() if r.fecha else None, "fecha_exacta": r.fecha_exacta,
                        "plaga": r.plaga, "notas": r.notas,
                        "hallazgos": sorted({(f.code, f.severity.name, f.market or "") for f in propios})}
                filas.append(fila)
                print(f"{r.pid}.{r.n:02d} {r.tipo:13} {r.via or '-':16} {(r.nombre_producto or '-')[:22]:22} "
                      f"{fila['fecha'] or '-':10} {'exacta' if r.fecha_exacta else 'aprox.'} {fila['hallazgos']} {r.notas}",
                      flush=True)
                if r.tipo != "no_plaguicida":
                    clave = (prog["cultivo"], crudo.get("producto") or crudo.get("ingrediente"))
                    it = items.setdefault(clave, {"cultivo": prog["cultivo"], "texto": clave[1],
                                                  "ingrediente_texto": crudo.get("ingrediente", ""),
                                                  "resuelto": r.nombre_producto or "(sin resolver)",
                                                  "ingredientes": ", ".join(r.ingredientes), "programas": set()})
                    it["programas"].add(prog["pid"])
            programas.append({"pid": prog["pid"], "cultivo": prog["cultivo"], "filas": len(rs),
                              "no_conforme": any(f.severity is Severity.BLOCKING for f in hallazgos),
                              "con_riesgo": any(f.severity is Severity.RISK for f in hallazgos),
                              "hallazgos": dict(Counter(f.code for f in hallazgos))})
    finally:
        gen.close()
    plag = [f for f in filas if f["tipo"] != "no_plaguicida"]
    resumen = {"programas": len(programas), "filas": len(filas), "filas_plaguicida": len(plag),
               "no_plaguicida": sum(f["tipo"] == "no_plaguicida" for f in filas),
               "resueltas_por_nombre": sum(f["via"] == "nombre_comercial" for f in plag if f["tipo"] == "plaguicida"),
               "resueltas_por_ingrediente": sum(f["via"] == "ingrediente" for f in plag if f["tipo"] == "plaguicida"),
               "no_resueltas": sum(f["tipo"] == "no_resuelta" for f in plag),
               "nombre_e_ingrediente_discrepan": sum(bool(f["discrepancia"]) for f in plag),
               "fechas_exactas": sum(f["fecha_exacta"] for f in plag), "fechas_aproximadas":
                   sum(bool(f["fecha"]) and not f["fecha_exacta"] for f in plag),
               "filas_con_bloqueante": sum(any(h[1] == "BLOCKING" for h in f["hallazgos"]) for f in plag),
               "filas_con_riesgo": sum(any(h[1] == "RISK" for h in f["hallazgos"]) for f in plag),
               "hallazgos": dict(Counter(h[0] for f in plag for h in f["hallazgos"])), "por_programa": programas}
    (run / "metricas.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    (run / "por_fila.jsonl").write_text("\n".join(json.dumps(f, ensure_ascii=False) for f in filas) + "\n",
                                        encoding="utf-8")
    if not REALES_REFERENCIA.exists():
        _hoja_referencia(list(items.values()))
    print(json.dumps({k: v for k, v in resumen.items() if k != "por_programa"}, ensure_ascii=False, indent=1))
    print(f"corrida: {run}\nreferencia: {REALES_REFERENCIA}")


def _hoja_referencia(items: list[dict]) -> None:
    """One row per product or ingredient (as the thesis writes it) and crop; the person fills the four columns from the
    public SENASA query (SIGIA) and the EU and US limits, without looking at the validator's findings."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    guia = wb.active
    guia.title = "Cómo llenar"
    for linea in [["Columna", "Qué poner (consultar SIGIA de SENASA y la base de LMR de la UE; EE. UU.: 40 CFR 180)"],
                  [REF_COLS[0], ("Sí / No. Uva: registrado para uva contra oídio. Palto: algún producto con ese ingrediente "
                                "registrado para palto (cualquier plaga). Si el nombre comercial no aparece, «No encontrado».")],
                  [REF_COLS[1], "Días de carencia del registro (uva: el del producto; palto: el más largo entre los registrados)."],
                  [REF_COLS[2], "específico / por defecto / no aprobado: el LMR de la UE para uva de mesa o palta."],
                  [REF_COLS[3], "Solo palto: sí (hay tolerancia) / no. En uva dejar en blanco."], [],
                  ["", "No mires los hallazgos del sistema antes de llenar: esta hoja es la referencia contra la que se mide."]]:
        guia.append(linea)
    guia.column_dimensions["A"].width, guia.column_dimensions["B"].width = 28, 110
    ws = wb.create_sheet("Referencia")
    ws.append(["Cultivo", "Como lo escribe la tesis", "Ingrediente (tesis)", "Producto que resolvió el sistema",
               "Ingredientes", "Programas", *REF_COLS])
    for col, w in zip("ABCDEFGHIJ", (11, 22, 26, 24, 26, 10, 16, 12, 16, 14)):
        ws.column_dimensions[col].width = w
    for c in ws[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="2F5D50")
        c.alignment = Alignment(wrap_text=True, vertical="center")
    amarillo = PatternFill("solid", fgColor="FFF6D5")
    for it in sorted(items, key=lambda x: (x["cultivo"], _plano_es(x["texto"]))):
        ws.append([{"table_grape": "uva de mesa", "avocado": "palto"}.get(it["cultivo"], it["cultivo"]), it["texto"],
                   it["ingrediente_texto"], it["resuelto"], it["ingredientes"], ", ".join(sorted(it["programas"])),
                   None, None, None, None])
        for col in (7, 8, 9, 10):
            ws.cell(ws.max_row, col).fill = amarillo
    for col, opciones in ((7, "Sí,No,No encontrado"), (9, "específico,por defecto,no aprobado"), (10, "sí,no")):
        dv = DataValidation(type="list", formula1=f'"{opciones}"', allow_blank=True)
        ws.add_data_validation(dv)
        letra = "ABCDEFGHIJ"[col - 1]
        dv.add(f"{letra}2:{letra}{ws.max_row}")
    ws.freeze_panes = "C2"
    wb.active = 1
    wb.save(REALES_REFERENCIA)


def _plano_es(t: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", t.lower()) if not unicodedata.combining(c))


HOJAS_REALES = SUITES / "programas_reales_hojas"
# column headers of the field sheets, as a technician writes them (grape programs have dates, avocado ones stages)
ENCABEZADOS = {"fecha": "Fecha", "momento": "Momento de aplicación", "producto": "Producto comercial",
               "ingrediente": "Ingrediente activo", "dosis": "Dosis", "objetivo": "Objetivo"}


def _hojas_reales(datos: dict) -> None:
    """The five real programs written as field sheets (one .xlsx each, the columns each table prints)."""
    from openpyxl import Workbook

    HOJAS_REALES.mkdir(parents=True, exist_ok=True)
    for prog in datos["programas"]:
        cols = [c for c in ENCABEZADOS if any(c in f for f in prog["filas"])]
        wb = Workbook()
        ws = wb.active
        ws.title = "Programa"
        ws.append([ENCABEZADOS[c] for c in cols])
        for f in prog["filas"]:
            ws.append([f.get(c) for c in cols])
        wb.save(HOJAS_REALES / f"{prog['pid']}.xlsx")


def importar_reales(args) -> None:
    """Stage E, rule 3 (pendientes/26): the five real programs, written as field sheets, go through the system's
    path (sheet reader, resolver, validator) instead of the evaluation's. It has to reproduce the resolution and the
    findings of run 2026-11-27_0405 row by row; it also reports the dose check (rows outside the registered dose)."""
    from collections import Counter

    from domain.findings import Severity
    from domain.validation.program import validate_program
    from knowledge.programs.importer import importar
    from knowledge.programs.sheets import leer_hoja

    datos = json.loads(REALES.read_text(encoding="utf-8"))
    if not HOJAS_REALES.exists() or args.rehacer_hojas:
        _hojas_reales(datos)
    antes = {(f["pid"], f["n"]): f for f in (json.loads(x) for x in (RUNS / args.contra / "por_fila.jsonl").read_text(
        encoding="utf-8").splitlines() if x.strip())}
    gen, src, res = _resolver_reales()
    run = RUNS / f"{datetime.now():%Y-%m-%d_%H%M}_importar_reales"
    run.mkdir(parents=True, exist_ok=True)
    filas, distintas = [], []
    campos = ("tipo", "via", "producto", "fecha", "fecha_exacta", "plaga", "hallazgos")
    try:
        for prog in datos["programas"]:
            hoja = HOJAS_REALES / f"{prog['pid']}.xlsx"
            imp = importar(leer_hoja(hoja.read_bytes(), hoja.name), nombre=prog["pid"], cultivo=prog["cultivo"],
                           mercados=prog["mercados"], cosecha=datetime.fromisoformat(prog["cosecha_evaluacion"]).date(),
                           resolvedor=res, plaga=prog.get("plaga_texto"), graph=src.limits.graph)
            hallazgos = ([f for f in validate_program(imp.programa, src.registry, src.limits, src.moa).findings
                          if f.severity is not Severity.INFO] if imp.programa else [])
            for x in imp.filas:
                r = x.resolucion
                propios = [f for f in hallazgos if r.producto and f.product_id == r.producto]
                fila = {"pid": prog["pid"], "n": x.n, "estado": x.estado, "tipo": r.tipo, "via": r.via,
                        "producto": r.producto, "nombre_producto": r.nombre_producto,
                        "fecha": r.fecha.isoformat() if r.fecha else None, "fecha_exacta": r.fecha_exacta,
                        "plaga": r.plaga, "notas": r.notas,
                        "hallazgos": [list(h) for h in sorted({(f.code, f.severity.name, f.market or "") for f in propios})],
                        "dosis": None if x.dosis is None else {"texto": x.dosis.texto, "estado": x.dosis.estado,
                                                                "motivo": x.dosis.motivo, "registradas": x.dosis.registradas},
                        "objetivo": x.original.get("objetivo"), "objetivo_plagas": list(r.objetivo_plagas),
                        "registro_objetivo": r.registro_objetivo}
                filas.append(fila)
                a = antes.get((prog["pid"], x.n)) or {}
                previo = lambda c, a=a: sorted(map(list, a.get(c) or [])) if c == "hallazgos" else a.get(c)
                dif = {c: (previo(c), fila[c]) for c in campos if not a or previo(c) != fila[c]}
                if dif:
                    distintas.append({"pid": prog["pid"], "n": x.n, "diferencias": dif})
                d = fila["dosis"] or {}
                print(f"{prog['pid']}.{x.n:02d} {x.estado:24} {(r.nombre_producto or '-')[:22]:22} {fila['fecha'] or '-':10} "
                      f"{d.get('estado', '-'):14} {d.get('texto') or '':12} {', '.join(d.get('registradas') or [])}",
                      flush=True)
    finally:
        gen.close()
    plag = [f for f in filas if f["tipo"] != "no_plaguicida"]
    dosis = [f for f in plag if f["dosis"]]
    resumen = {"contra": args.contra, "hojas": str(HOJAS_REALES), "filas": len(filas), "filas_plaguicida": len(plag),
               "resueltas": sum(f["tipo"] == "plaguicida" for f in plag),
               "necesitan_persona": sum(f["estado"] == "necesita_persona" for f in filas),
               "filas_iguales_a_la_corrida": len(filas) - len(distintas), "filas_distintas": distintas,
               "reproduce": not distintas and len(filas) == len(antes),
               "dosis": {e: sum(f["dosis"]["estado"] == e for f in dosis) for e in ("dentro", "fuera_de_rango", "no_comparable")},
               "dosis_fuera_de_rango": [{"pid": f["pid"], "n": f["n"], "producto": f["nombre_producto"],
                                         "dosis": f["dosis"]["texto"], "registradas": f["dosis"]["registradas"]}
                                        for f in dosis if f["dosis"]["estado"] == "fuera_de_rango"],
               "dosis_no_comparables_por_motivo": dict(Counter(
                   f["dosis"]["motivo"] for f in dosis if f["dosis"]["estado"] == "no_comparable")),
               # the row's objective read as pests (rule 4 of stage E): a flag for review, the validation is unchanged
               "objetivo": dict(Counter(f["registro_objetivo"] for f in filas if f["registro_objetivo"])),
               "objetivo_no_registrado": [{"pid": f["pid"], "n": f["n"], "producto": f["nombre_producto"],
                                           "objetivo": f["objetivo"], "plagas": f["objetivo_plagas"]}
                                          for f in filas if f["registro_objetivo"] == "no_registrado"],
               "objetivo_sin_resolver": sorted({f["objetivo"] for f in filas if f["registro_objetivo"] == "sin_resolver"})}
    (run / "metricas.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    (run / "por_fila.jsonl").write_text("\n".join(json.dumps(f, ensure_ascii=False) for f in filas) + "\n",
                                        encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=1))
    print(f"corrida: {run}")


def reales_acuerdo(args) -> None:
    """The validator against the reference set by hand, per row of the real programs: whether the row has a blocking
    problem (not registered, or the pre-harvest interval not met by the assumed harvest) and whether it carries a market
    risk (no specific EU limit, or no US tolerance), with agreement, precision and recall of the validator."""
    from datetime import date, timedelta

    from openpyxl import load_workbook

    from evaluation.fidelidad import cohen_kappa

    datos = {p["pid"]: p for p in json.loads(REALES.read_text(encoding="utf-8"))["programas"]}
    ws = load_workbook(REALES_REFERENCIA, read_only=True, data_only=True)["Referencia"]
    filas_x = ws.iter_rows(values_only=True)
    cab = list(next(filas_x))
    ref = {}
    for f in filas_x:
        d = dict(zip(cab, f))
        cultivo = {"uva de mesa": "table_grape", "palto": "avocado"}.get(d["Cultivo"], d["Cultivo"])
        ref[(cultivo, d["Como lo escribe la tesis"])] = d
    adjudicadas = []
    if args.adjudicada:          # rows resolved against the official source (27/11/2026); the sheet is not modified
        adj = json.loads((SUITES / "programas_reales_adjudicacion.json").read_text(encoding="utf-8"))
        for c in adj["correcciones"]:
            fila = ref[(c["cultivo"], c["texto"])]
            assert str(fila[c["columna"]]).strip().lower() == c["original"].lower(), c
            ref[(c["cultivo"], c["texto"])] = {**fila, c["columna"]: c["adjudicado"]}
            adjudicadas.append(f"{c['cultivo']}:{c['texto']}:{c['columna']}")
    corrida = [json.loads(x) for x in (RUNS / args.corrida / "por_fila.jsonl").read_text(encoding="utf-8").splitlines() if x]
    pares = {"bloqueante": ([], []), "riesgo_mercado": ([], [])}
    detalle = []
    for f in corrida:
        if f["tipo"] == "no_plaguicida":
            continue
        prog = datos[f["pid"]]
        crudo = prog["filas"][f["n"] - 1]
        d = ref.get((prog["cultivo"], crudo.get("producto") or crudo.get("ingrediente")))
        if not d or not d.get(REF_COLS[0]):
            continue
        cosecha = date.fromisoformat(prog["cosecha_evaluacion"])
        carencia = d.get(REF_COLS[1])
        no_reg = str(d[REF_COLS[0]]).strip().lower() != "sí"
        phi = (f["fecha"] is not None and isinstance(carencia, (int, float))
               and date.fromisoformat(f["fecha"]) + timedelta(days=int(carencia)) > cosecha)
        mercado = (("EU" in prog["mercados"] and str(d.get(REF_COLS[2]) or "").strip().lower() in ("por defecto", "no aprobado"))
                   or ("US" in prog["mercados"] and str(d.get(REF_COLS[3]) or "").strip().lower() == "no"))
        esperado = {"bloqueante": no_reg or phi, "riesgo_mercado": (not no_reg) and mercado}
        codigos = {h[0] for h in f["hallazgos"]}
        sistema = {"bloqueante": f["tipo"] == "no_resuelta" or any(h[1] == "BLOCKING" for h in f["hallazgos"]),
                   # every market-limit risk the validator emits: the EU lists a non-approved substance at the limit
                   # of quantification, so it arrives as LIMIT_AT_LOQ, not as DEFAULT_LIMIT (fixed 26/11/2026, the
                   # first comparison left it out)
                   "riesgo_mercado": bool(codigos & {"DEFAULT_LIMIT", "NOT_PERMITTED", "LIMIT_AT_LOQ",
                                                     "LIMIT_WITHOUT_VALUE"})}
        for k in pares:
            pares[k][0].append(esperado[k])
            pares[k][1].append(sistema[k])
        detalle.append({"fila": f"{f['pid']}.{f['n']}", "texto": f["texto"], "esperado": esperado, "sistema": sistema,
                        "hallazgos": f["hallazgos"], "tipo": f["tipo"]})
    out = {"corrida": args.corrida, "referencia": "adjudicada" if args.adjudicada else "original",
           "correcciones": adjudicadas, "filas_comparadas": len(detalle)}
    for k, (e, s) in pares.items():
        tp = sum(a and b for a, b in zip(e, s))
        out[k] = {"referencia_positivas": sum(e), "sistema_positivas": sum(s), "coinciden": sum(a == b for a, b in zip(e, s)),
                  "precision": round(tp / sum(s), 3) if sum(s) else None,
                  "exhaustividad": round(tp / sum(e), 3) if sum(e) else None, "kappa": cohen_kappa(e, s)}
    run = RUNS / (f"{datetime.now():%Y-%m-%d_%H%M}_acuerdo_reales" + ("_adjudicada" if args.adjudicada else ""))
    run.mkdir(parents=True, exist_ok=True)
    (run / "metricas.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    (run / "por_fila.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in detalle) + "\n",
                                        encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"corrida: {run}")


def validar_controles(args) -> None:
    """S3 controls (review of 26/11/2026): clean programs and near misses at the edges of the rules, labelled by the
    rules themselves (evaluation/programs.py), never by the validator. A program is right when the validator's blocking
    findings and rotation findings are exactly the expected ones."""
    from collections import Counter, defaultdict
    from datetime import date

    from domain.findings import Severity
    from domain.validation.models import Application, Block, Program
    from domain.validation.program import validate_program
    from evaluation.programs import ControlSuiteBuilder
    from interfaces.api.sources import graph_sources

    archivo = SUITES / "programas_control.jsonl"
    gen = graph_sources()
    src = next(gen)
    try:
        if not archivo.exists():
            casos = ControlSuiteBuilder(src.limits.graph, src).build_controls(args.n)
            archivo.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in casos) + "\n", encoding="utf-8")
        casos = [json.loads(x) for x in archivo.read_text(encoding="utf-8").splitlines() if x.strip()]
        run = RUNS / f"{datetime.now():%Y-%m-%d_%H%M}_validador_controles"
        run.mkdir(parents=True, exist_ok=True)
        por_tipo, filas = defaultdict(Counter), []
        for c in casos:
            pr = c["programa"]
            prog = Program(pr["crop"], tuple(Block(b["key"], date.fromisoformat(b["harvest_on"]), tuple(b["markets"]))
                                             for b in pr["blocks"]),
                           tuple(Application(a["block"], a["product_id"], date.fromisoformat(a["applied_on"]), a.get("pest"))
                                 for a in pr["applications"]))
            hallados = {(f.code, f.block, f.product_id) for f in validate_program(prog, src.registry, src.limits, src.moa).findings
                        if f.severity is Severity.BLOCKING or f.code == "ROTATION_SAME_GROUP"}
            esperados = {(e["code"], e["block"], e["product_id"]) for e in c["esperadas"]}
            ok = hallados == esperados
            t = por_tipo[c["tipo"]]
            t["programas"] += 1
            t["correctos"] += ok
            t["falsas_alarmas"] += len(hallados - esperados)
            t["omitidos"] += len(esperados - hallados)
            filas.append({"pid": c["pid"], "tipo": c["tipo"], "correcto": ok, "esperados": sorted(map(list, esperados)),
                          "hallados": sorted(map(list, hallados)), "descripcion": c["descripcion"]})
            print(f"{c['pid']} {c['tipo']:18} {'ok ' if ok else 'MAL'} esperados={sorted(esperados)} hallados={sorted(hallados)}",
                  flush=True)
    finally:
        gen.close()
    total = Counter()
    for t in por_tipo.values():
        total.update(t)
    resumen = {"programas": len(casos), "correctos": total["correctos"], "falsas_alarmas": total["falsas_alarmas"],
               "omitidos": total["omitidos"], "por_tipo": {k: dict(v) for k, v in por_tipo.items()}}
    (run / "metricas.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    (run / "por_programa.jsonl").write_text("\n".join(json.dumps(f, ensure_ascii=False) for f in filas) + "\n",
                                            encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=1))
    print(f"corrida: {run}")


def comparar_recuperacion(args) -> None:
    """Paired tests between the retrievers of one ``recuperacion-juzgada`` run (rule of 27/11/2026): exact McNemar on
    useful@10 and useful@1 per question, and Wilcoxon on MRR@10, hybrid against dense and against lexical."""
    from evaluation.comparacion import mcnemar_exacta, wilcoxon

    filas = [json.loads(x) for x in (RUNS / args.corrida / "por_pregunta.jsonl").read_text(encoding="utf-8").splitlines()
             if x.strip()]
    por = {}
    for f in filas:
        por.setdefault(f["lista"].split("/")[1], {})[f["qid"]] = f
    out = {"corrida": args.corrida}
    for otro in ("denso", "lexico"):
        q = sorted(set(por["hibrido"]) & set(por[otro]))
        h, o = por["hibrido"], por[otro]
        out[f"hibrido_vs_{otro}"] = {
            "preguntas": len(q),
            "util@10": {"hibrido": sum(h[k]["util@10"] for k in q), otro: sum(o[k]["util@10"] for k in q),
                        **mcnemar_exacta([h[k]["util@10"] == 1 for k in q], [o[k]["util@10"] == 1 for k in q])},
            "util@1": {"hibrido": sum(h[k]["util@1"] for k in q), otro: sum(o[k]["util@1"] for k in q),
                       **mcnemar_exacta([h[k]["util@1"] == 1 for k in q], [o[k]["util@1"] == 1 for k in q])},
            "mrr@10": {"hibrido": round(sum(h[k]["mrr@10"] for k in q) / len(q), 3),
                       otro: round(sum(o[k]["mrr@10"] for k in q) / len(q), 3),
                       **wilcoxon([h[k]["mrr@10"] for k in q], [o[k]["mrr@10"] for k in q])}}
    run = RUNS / f"{datetime.now():%Y-%m-%d_%H%M}_comparacion_recuperacion"
    run.mkdir(parents=True, exist_ok=True)
    (run / "metricas.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"corrida: {run}")


VALIDADOR_LLM = """Eres un técnico de cumplimiento fitosanitario en el Perú. Recibes un programa de aplicaciones de
plaguicidas de un cultivo: bloques con su fecha de cosecha y mercados de destino, y aplicaciones con bloque, producto
(nombre comercial e ingredientes), fecha y plaga objetivo. Revisa el programa con estas reglas y lista cada
incumplimiento:
NOT_REGISTERED: el producto no tiene registro en SENASA para ese cultivo y esa plaga.
PHI_NOT_MET: entre la aplicación y la cosecha del bloque pasan menos días que el periodo de carencia registrado.
APPLIED_AFTER_HARVEST: la aplicación es posterior a la cosecha del bloque.
ROTATION_SAME_GROUP: dos aplicaciones consecutivas en un bloque tienen el mismo grupo de modo de acción (FRAC o IRAC).
UNKNOWN_BLOCK: la aplicación indica un bloque que no está en el programa.
Responde solo JSON: {"incumplimientos": [{"codigo": "...", "bloque": "...", "producto": "nombre comercial"}]}; lista
vacía si el programa cumple."""


def validar_llm(args) -> None:
    """Baseline for S3 (rule of 27/11/2026): the same local model without the exact core reviews each program from its
    own knowledge, given the trade names and ingredients of its products and the rules the validator checks. Scored as
    the validator: seeded violations by code, block and product; controls by their exact expected set."""
    from collections import Counter
    from datetime import date

    from assistant.config import load_assistant_config
    from domain.findings import Severity
    from domain.validation.models import Application, Block, Program
    from domain.validation.program import validate_program
    from evaluation.comparacion import mcnemar_exacta
    from evaluation.fidelidad import Juez
    from interfaces.api.sources import graph_sources

    local = load_assistant_config().generators.get("local", {})
    modelo = args.modelo or local.get("model", "qwen3:8b")
    llm = Juez(local.get("base_url", "http://localhost:11434/v1"), modelo, num_ctx=8192)
    sembrados = SUITES / "programas.jsonl"
    casos = [] if args.solo_controles or not sembrados.exists() else [
        ("sembrado", json.loads(x)) for x in sembrados.read_text(encoding="utf-8").splitlines() if x]
    casos += [("control", json.loads(x)) for x in (SUITES / "programas_control.jsonl").read_text(encoding="utf-8").splitlines() if x]
    gen = graph_sources()
    src = next(gen)
    run = RUNS / (f"{datetime.now():%Y-%m-%d_%H%M}_validador_llm_{modelo.replace(':', '-').replace('.', '_')}"
                  + ("_controles" if not any(t == "sembrado" for t, _ in casos) else ""))
    run.mkdir(parents=True, exist_ok=True)
    filas, totales = [], Counter()
    try:
        plagas = {k: f"{c or ''} ({s or ''})".strip() for k, c, s in src.limits.graph.run(
            "MATCH (p:Pest) RETURN p.key, p.common_name, p.scientific_name", columns=("k", "c", "s"))}
        for tipo, c in casos:
            pr = c["programa"]
            nombres, texto_apps = {}, []
            for a in pr["applications"]:
                reg = src.registry.product(a["product_id"])
                nombre = reg.trade_name if reg else a["product_id"]
                nombres[nombre.strip().lower()] = a["product_id"]
                ing = ", ".join(reg.ingredients) if reg else "?"
                texto_apps.append(f"- bloque {a['block']}: {nombre} ({ing}), aplicado el {a['applied_on']}, "
                                  f"contra {plagas.get(a.get('pest'), a.get('pest'))}")
            texto = (f"Cultivo: {pr['crop']}\nBloques:\n" + "\n".join(
                f"- {b['key']}: cosecha {b['harvest_on']}, mercados {', '.join(b['markets'])}" for b in pr["blocks"])
                + "\nAplicaciones:\n" + "\n".join(texto_apps))
            m = re.search(r"\{.*\}", llm.chat(VALIDADOR_LLM, texto), re.DOTALL)
            try:
                dichos = json.loads(m.group(0)).get("incumplimientos", []) if m else []
            except json.JSONDecodeError:
                dichos = []
            hallados = set()
            for d in dichos if isinstance(dichos, list) else []:
                if not isinstance(d, dict):
                    continue
                pid = nombres.get(str(d.get("producto", "")).strip().lower())
                if pid is None:     # a name the model shortened: match by prefix
                    pid = next((v for k, v in nombres.items() if str(d.get("producto", "")).strip().lower()[:6] in k), None)
                hallados.add((str(d.get("codigo", "")).strip().upper(), str(d.get("bloque", "")).strip(), pid))
            # the validator on the same program, for the paired comparison
            prog = Program(pr["crop"], tuple(Block(b["key"], date.fromisoformat(b["harvest_on"]), tuple(b["markets"]))
                                             for b in pr["blocks"]),
                           tuple(Application(a["block"], a["product_id"], date.fromisoformat(a["applied_on"]), a.get("pest"))
                                 for a in pr["applications"]))
            val = {(f.code, f.block, f.product_id) for f in validate_program(prog, src.registry, src.limits, src.moa).findings
                   if f.severity is Severity.BLOCKING or f.code == "ROTATION_SAME_GROUP"}
            if tipo == "sembrado":
                esperados = {(s["code"], s["block"], s["product_id"]) for s in c["sembradas"]}
                validos = esperados | {(s["code"], s["block"], s["product_id"]) for s in c.get("colaterales", [])}
                totales["sembradas"] += len(esperados)
                totales["llm_detectadas"] += len(esperados & hallados)
                totales["llm_hallazgos"] += len(hallados)
                totales["llm_correctos"] += len(hallados & validos)
                ok_llm, ok_val = esperados <= hallados, esperados <= val
            else:
                esperados = {(e["code"], e["block"], e["product_id"]) for e in c["esperadas"]}
                ok_llm, ok_val = hallados == esperados, val == esperados
                if c["tipo"] == "LIMPIO":
                    totales["limpios"] += 1
                    totales["llm_falsas_alarmas_limpios"] += bool(hallados)
            totales[f"{tipo}_programas"] += 1
            totales[f"{tipo}_llm_correctos"] += ok_llm
            totales[f"{tipo}_validador_correctos"] += ok_val
            filas.append({"pid": c["pid"], "tipo": tipo, "llm_correcto": ok_llm, "validador_correcto": ok_val,
                          "esperados": sorted(map(list, esperados), key=str), "llm": sorted(map(list, hallados), key=str)})
            print(f"{c['pid']} {tipo:9} llm={'ok ' if ok_llm else 'MAL'} validador={'ok' if ok_val else 'MAL'}", flush=True)
    finally:
        gen.close()
    pares = mcnemar_exacta([f["validador_correcto"] for f in filas], [f["llm_correcto"] for f in filas])
    res = {"modelo": modelo, **dict(totales),
           "llm_exhaustividad_sembradas": round(totales["llm_detectadas"] / totales["sembradas"], 3) if totales["sembradas"] else None,
           "llm_precision_sembradas": round(totales["llm_correctos"] / totales["llm_hallazgos"], 3) if totales["llm_hallazgos"] else None,
           "programas_correctos_validador": sum(f["validador_correcto"] for f in filas),
           "programas_correctos_llm": sum(f["llm_correcto"] for f in filas), "programas": len(filas),
           "mcnemar_validador_vs_llm": pares}
    (run / "metricas.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    (run / "por_programa.jsonl").write_text("\n".join(json.dumps(f, ensure_ascii=False) for f in filas) + "\n",
                                            encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"corrida: {run}")


def _rag_convencional(base_url: str, modelo: str):
    """The conventional RAG baseline over the deployed retriever (V7), with the same local model and no tools."""
    from assistant.answer import build_answerer
    from assistant.config import load_assistant_config
    from assistant.generation.generators import LocalGenerator
    from evaluation.rag_baseline import RagConvencional
    from knowledge.corpus.store import CorpusStore, connect, migrate

    conn = connect()
    migrate(conn)
    retriever = build_answerer(CorpusStore(conn), load_assistant_config()).retriever
    gen = LocalGenerator(base_url=base_url, model=modelo, temperature=0, max_output_tokens=1024, think=False)
    return RagConvencional(retriever, gen)


REVISION = SUITES / "textual_revision_anotacion.xlsx"
REVISION_COLS = ("¿Se entiende sola?", "¿El fragmento la responde?", "¿La haría un técnico?")


def revision_preguntas(args) -> None:
    """The researcher's review of a sample of the textual questions (rule in pendientes/26, 27/11/2026): 20 of the 60,
    stratified like the suite (13 single-hop, 7 multi-hop), each with its reference passages, document and page, and
    three judgments to fill: understood without the page, answered by the passage (yes, partly, no), asked by a
    technician. The sheet shows corpus passages, so it is not published."""
    import random

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    from knowledge.corpus.store import connect

    if REVISION.exists() and not args.forzar:
        raise SystemExit(f"{REVISION} ya existe (puede tener respuestas); usa --forzar para rehacerlo")
    items = _s2_items()
    rng = random.Random(20261127)
    simples = [i for i in items if i["tipo"] != "varios_saltos"]
    multi = [i for i in items if i["tipo"] == "varios_saltos"]
    toma = sorted(rng.sample(simples, 13) + rng.sample(multi, 7), key=lambda i: i["qid"])
    titulos = dict(connect().execute("SELECT doc_id, titulo FROM documentos").fetchall())
    wb = Workbook()
    guia = wb.active
    guia.title = "Cómo revisar"
    for linea in [["Columna", "Qué poner"],
                  [REVISION_COLS[0], "sí / no: un técnico la entiende sin ver la página (nombra el cultivo, la plaga o el tema)."],
                  [REVISION_COLS[1], "sí / en parte / no: el fragmento de referencia contiene la respuesta (en varios saltos, entre los dos)."],
                  [REVISION_COLS[2], "sí / no: es una pregunta que alguien de sanidad vegetal haría de verdad."],
                  ["Comentario", "Opcional: qué falla, si algo falla."], [],
                  ["", "Juzga solo la pregunta y su fragmento; no hace falta saber la respuesta de memoria."]]:
        guia.append(linea)
    guia.column_dimensions["A"].width, guia.column_dimensions["B"].width = 28, 100
    guia["A1"].font = guia["B1"].font = Font(bold=True)
    ws = wb.create_sheet("Revisar")
    ws.append(["N.°", "Pregunta", "Tipo", "Documento y página", "Fragmento de referencia", "Respuesta de referencia",
               *REVISION_COLS, "Comentario", "id"])
    for col, w in zip("ABCDEFGHIJK", (5, 40, 11, 30, 70, 35, 13, 15, 13, 30, 4)):
        ws.column_dimensions[col].width = w
    ws.column_dimensions["K"].hidden = True
    for c in ws[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="2F5D50")
    amarillo, ajuste = PatternFill("solid", fgColor="FFF6D5"), Alignment(wrap_text=True, vertical="top")
    for n, it in enumerate(toma, 1):
        ev = it.get("evidencias") or []
        donde = "\n".join(f"{titulos.get(e['doc_id'], e['doc_id'])}, p. {e.get('pagina')}" for e in ev)
        frag = "\n\n".join(" ".join(str(e.get("fragmento", "")).split()) for e in ev)
        ws.append([n, it["pregunta"], "varios saltos" if it["tipo"] == "varios_saltos" else "un salto", donde, frag,
                   it.get("respuesta", ""), None, None, None, None, it["qid"]])
        r = ws.max_row
        for c in ws[r]:
            c.alignment = ajuste
        for col in (7, 8, 9, 10):
            ws.cell(r, col).fill = amarillo
        ws.row_dimensions[r].height = min(409, 15 * (max(len(frag) // 60, len(it["pregunta"]) // 35, 2) + 1))
    for rango, opciones in (("G2:G21", "sí,no"), ("H2:H21", "sí,en parte,no"), ("I2:I21", "sí,no")):
        dv = DataValidation(type="list", formula1=f'"{opciones}"', allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(rango)
    ws.freeze_panes = "C2"
    wb.active = 1
    wb.save(REVISION)
    print(json.dumps({"preguntas": len(toma), "un_salto": 13, "varios_saltos": 7, "semilla": 20261127,
                      "qids": [i["qid"] for i in toma]}, ensure_ascii=False))
    print(REVISION)


def revision_resultado(args) -> None:
    """Summary of the question review: how many pass the three judgments, with a Wilson 95 % interval, and which fail."""
    import math

    from openpyxl import load_workbook

    ws = load_workbook(REVISION, read_only=True)["Revisar"]
    filas = list(ws.iter_rows(values_only=True))
    cab = list(filas[0])
    idx = [cab.index(c) for c in REVISION_COLS]
    hechas, validas, fallan = 0, 0, []
    norm = lambda v: str(v or "").strip().lower()
    for f in filas[1:]:
        valores = [norm(f[i]) for i in idx]
        if not all(valores):
            continue
        hechas += 1
        if valores == ["sí", "sí", "sí"]:
            validas += 1
        else:
            fallan.append({"qid": f[cab.index("id")], "juicios": dict(zip(REVISION_COLS, valores)),
                           "comentario": f[cab.index("Comentario")]})
    z = 1.96
    if hechas:
        p_ = validas / hechas
        centro = (p_ + z * z / (2 * hechas)) / (1 + z * z / hechas)
        margen = z * math.sqrt(p_ * (1 - p_) / hechas + z * z / (4 * hechas * hechas)) / (1 + z * z / hechas)
        ic = [round(centro - margen, 3), round(centro + margen, 3)]
    else:
        ic = None
    res = {"revisadas": hechas, "validas": validas, "wilson_95": ic, "no_validas": fallan}
    run = RUNS / f"{datetime.now():%Y-%m-%d_%H%M}_revision_preguntas"
    run.mkdir(parents=True, exist_ok=True)
    (run / "metricas.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"corrida: {run}")


def resumen_estadistico(args) -> None:
    """Holm-adjusted p-values for the family of tests the paper reports, and 95 % intervals of its main estimates
    (rule in pendientes/26, 27/11/2026). Every p-value is read from the run that computed it; the coverage tests are
    recomputed here from the answers. Wilson for proportions, percentile bootstrap (10 000, fixed seed) for means."""
    import statistics

    from evaluation.comparacion import mcnemar_exacta
    from evaluation.estadistica import bootstrap_media, holm, wilson

    def leer(run: str) -> dict:
        return json.loads((RUNS / run / "metricas.json").read_text(encoding="utf-8"))

    def en(d: dict, *ruta):
        for k in ruta:
            d = d[k]
        return float(d)

    def filas(run: str, archivo: str = "respuestas.jsonl") -> dict:
        return {json.loads(x)["qid"]: json.loads(x) for x in (RUNS / run / archivo).read_text(encoding="utf-8").splitlines()
                if x.strip()}

    sis, rag = filas("2026-11-26_2015_fidelidad_s2_qwen3-8b"), filas("2026-11-26_1951_fidelidad_s2_rag_qwen3-8b")
    q = sorted(set(sis) & set(rag))
    mh = [k for k in q if sis[k]["tipo"] == "varios_saltos"]
    cob = mcnemar_exacta([bool(sis[k]["evidencia"]) for k in q], [bool(rag[k]["evidencia"]) for k in q])
    cob_mh = mcnemar_exacta([bool(sis[k]["evidencia"]) for k in mh], [bool(rag[k]["evidencia"]) for k in mh])
    ver = leer("2026-11-27_1419_acuerdo_verificacion")["corridas"]
    qwen_ver = ver["2026-11-27_0042_fidelidad_s2_ver-gemma4-e4b_qwen3-8b"]
    gemma_ver = ver["2026-11-27_0120_fidelidad_s2_gen-gemma4-e4b_ver-qwen3-8b_qwen3-8b"]
    s1q, s1g = leer("2026-11-24_2331_comparacion")["s1"], leer("2026-11-27_0254_comparacion")["s1"]
    rec = leer("2026-11-27_0004_comparacion_recuperacion")
    familia = [
        ("S1 Qwen3-8B: input guard only vs both", en(leer("2026-11-27_0039_comparacion")["s1"], "2026-11-24_1012_cumplimiento_s1_herramientas", "p")),
        ("S1 Qwen3-8B: no guards vs both", en(s1q, "2026-11-24_2321_cumplimiento_s1_sin-guarda", "p")),
        ("S1 Qwen3-8B: conventional RAG vs system", en(s1q, "2026-11-24_2323_cumplimiento_s1_rag", "p")),
        ("S1 Qwen3-8B: from memory vs system", en(s1q, "2026-11-24_0957_cumplimiento_s1_memoria", "p")),
        ("S1 Gemma 4 E4B: input guard only vs both", en(s1g, "2026-11-26_2321_cumplimiento_s1_herramientas_gen-gemma4-e4b", "p")),
        ("S1 Gemma 4 E4B: no guards vs both", en(s1g, "2026-11-26_2324_cumplimiento_s1_sin-guarda_gen-gemma4-e4b", "p")),
        ("S1 Gemma 4 E4B: conventional RAG vs system", en(s1g, "2026-11-26_2358_cumplimiento_s1_rag_gen-gemma4-e4b", "p")),
        ("S1 Gemma 4 E4B: from memory vs system", en(s1g, "2026-11-26_2357_cumplimiento_s1_memoria_gen-gemma4-e4b", "p")),
        ("S1b Gemma 4 E4B: eight vs six tools (0 -> 31)", mcnemar_exacta([True] * 31, [False] * 31)["p"]),
        ("S1b Qwen3-8B: eight vs six tools (0 -> 26)", mcnemar_exacta([True] * 26 + [False] * 5, [False] * 31)["p"]),
        ("Retrieval: hybrid vs lexical, useful@10", en(rec, "hibrido_vs_lexico", "util@10", "p")),
        ("Retrieval: hybrid vs lexical, useful@1", en(rec, "hibrido_vs_lexico", "util@1", "p")),
        ("Retrieval: hybrid vs lexical, MRR@10", en(rec, "hibrido_vs_lexico", "mrr@10", "p")),
        ("Retrieval: hybrid vs dense, useful@10", en(rec, "hibrido_vs_denso", "util@10", "p")),
        ("Retrieval: hybrid vs dense, MRR@10", en(rec, "hibrido_vs_denso", "mrr@10", "p")),
        ("Chunking: small to big vs base, useful@1 (test)", 0.34),
        ("Chunking: small to big vs base, MRR@10 (test)", 0.34),
        ("S2: answered, system vs conventional RAG", cob["p"]),
        ("S2: answered multi-hop, system vs conventional RAG", cob_mh["p"]),
        ("S2 faithfulness, both answered, Qwen3-8B judge", en(leer("2026-11-26_2038_comparacion"), "s2", "p")),
        ("S2 faithfulness, both answered, Gemma 4 E4B judge", en(leer("2026-11-26_2039_comparacion"), "s2", "p")),
        ("S2 faithfulness, both answered, Llama 3.1 8B judge", en(leer("2026-11-26_2041_comparacion"), "s2", "p")),
        ("Check, Qwen3-8B generator: Qwen3-8B judge", en(leer("2026-11-27_0111_comparacion"), "s2", "p")),
        ("Check, Qwen3-8B generator: Gemma 4 E4B judge (verifier)", en(leer("2026-11-27_0115_comparacion"), "s2", "p")),
        ("Check, Qwen3-8B generator: Llama 3.1 8B judge", en(leer("2026-11-27_0119_comparacion"), "s2", "p")),
        ("Check, Qwen3-8B generator: manual annotation", float(qwen_ver["pareadas"]["wilcoxon_p"])),
        ("Check, Qwen3-8B generator: answered", en(leer("2026-11-27_0111_comparacion"), "s2", "cobertura", "p")),
        ("Check, Gemma 4 E4B generator: Qwen3-8B judge (verifier)", en(leer("2026-11-27_0145_comparacion"), "s2", "p")),
        ("Check, Gemma 4 E4B generator: Gemma 4 E4B judge", en(leer("2026-11-27_0149_comparacion"), "s2", "p")),
        ("Check, Gemma 4 E4B generator: Llama 3.1 8B judge", en(leer("2026-11-27_0154_comparacion"), "s2", "p")),
        ("Check, Gemma 4 E4B generator: manual annotation", float(gemma_ver["pareadas"]["wilcoxon_p"])),
        ("Search per part: answered (test)", en(leer("2026-11-27_0247_comparacion"), "s2", "cobertura", "p")),
        ("Graph list end to end: answered, Qwen3-8B (test)", en(leer("2026-11-27_1600_comparacion_D3_prueba"), "Qwen3-8B (verificador Gemma)", "p_respondidas")),
        ("Validator vs same model without the exact core (42 controls)", mcnemar_exacta([True] * 42, [True] * 11 + [False] * 31)["p"]),
    ]
    ajust = holm([pv for _, pv in familia])
    tests = [{"prueba": n, "p": pv, "p_holm": float(f"{a:.3g}"), "antes": pv < 0.05, "despues": a < 0.05}
             for (n, pv), a in zip(familia, ajust)]

    def prop(nombre, k, n):
        lo, hi = wilson(k, n)
        return {"estimacion": nombre, "valor": f"{k}/{n}", "proporcion": round(k / n, 3), "ic95": [round(lo, 3), round(hi, 3)]}

    def media(nombre, valores):
        lo, hi = bootstrap_media(valores)
        return {"estimacion": nombre, "n": len(valores), "media": round(statistics.fmean(valores), 3),
                "ic95": [round(lo, 3), round(hi, 3)]}

    recup = [json.loads(x) for x in (RUNS / "2026-11-26_2016_recuperacion_juzgada" / "por_pregunta.jsonl").read_text(
        encoding="utf-8").splitlines() if x.strip()]
    hib = [x for x in recup if x["lista"] == "idf/hibrido"]
    gemma_juez = [x["fidelidad"] for x in filas("2026-11-26_2029_rejuicio_s2_gemma4-e4b").values() if x["fidelidad"] is not None]
    humano = _anotacion(FIDELIDAD_MUESTRA)
    por_q: dict[str, list[bool]] = {}
    for k, v in humano.items():
        por_q.setdefault(k.split(":")[0], []).append(v == "respaldada")
    manual_2611 = [statistics.fmean(v) for v in por_q.values()]
    antes = lambda c: [f["antes"] for f in c["por_respuesta"] if f["antes"] is not None]
    despues = lambda c: [f["despues"] for f in c["por_respuesta"] if f["despues"] is not None]
    rev = leer("2026-11-27_1704_revision_preguntas")
    intervalos = [
        prop("S1 exact, system (each model)", 110, 110),
        prop("S1 exact, from memory, Qwen3-8B", 8, 110), prop("S1 exact, conventional RAG, Qwen3-8B", 2, 110),
        prop("S1b (second suite) exact, eight tools, Gemma 4 E4B", 30, 31), prop("S1b (second suite) exact, eight tools, Qwen3-8B", 26, 31),
        prop("S2 useful@10, hybrid", round(sum(x["util@10"] for x in hib)), len(hib)),
        media("S2 MRR@10, hybrid", [x["mrr@10"] for x in hib]),
        prop("S2 answered, system", 50, 60), prop("S2 answered, conventional RAG", 36, 60),
        prop("S2 multi-hop answered, system", 16, 20), prop("S2 multi-hop answered, conventional RAG", 7, 20),
        media("S2 faithfulness, system, Gemma 4 E4B judge", gemma_juez),
        media("S2 faithfulness, system, manual (26/11 sample)", manual_2611),
        media("Manual faithfulness, Qwen3-8B before the check", antes(qwen_ver)),
        media("Manual faithfulness, Qwen3-8B after the check", despues(qwen_ver)),
        media("Manual faithfulness, Gemma 4 E4B before the check", antes(gemma_ver)),
        prop("Multi-hop test questions with both documents, graph list", 2, 14),
        prop("Validator, control programs decided correctly", 42, 42),
        prop("Same model without the exact core, control programs", 11, 42),
        prop("Real programs, blocking agreement (original reference)", 51, 54),
        prop("Real programs, blocking agreement (adjudicated)", 54, 54),
        prop("Reviewed questions valid on all three checks", int(rev["validas"]), int(rev["revisadas"])),
        prop("Reviewed questions fully answered by their passage", 9, 20),
    ]
    res = {"familia": len(tests), "significativas_antes": sum(t["antes"] for t in tests),
           "significativas_despues": sum(t["despues"] for t in tests),
           "cambian": [t["prueba"] for t in tests if t["antes"] != t["despues"]], "pruebas": tests, "intervalos": intervalos}
    run = RUNS / f"{datetime.now():%Y-%m-%d_%H%M}_resumen_estadistico"
    run.mkdir(parents=True, exist_ok=True)
    (run / "metricas.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k not in ("pruebas", "intervalos")}, ensure_ascii=False, indent=1))
    for t in tests:
        print(f"  {t['p']:.2e} -> {t['p_holm']:.2e} {'*' if t['despues'] else ' '} {t['prueba']}")
    for i in intervalos:
        print(f"  {i['estimacion']}: {i.get('valor') or i.get('media')} [{i['ic95'][0]}, {i['ic95'][1]}]")
    print(f"corrida: {run}")


def suite_s1b(args) -> None:
    """S1b (27/11/2026): list and count questions for the generic tools, built from the graph with their own queries."""
    from datetime import date

    from evaluation.generic_suite import build
    from knowledge.graph.age import AgeGraph

    excluir = frozenset()
    if args.excluir:
        previas = [json.loads(x) for x in (SUITES / args.excluir).read_text(encoding="utf-8").splitlines() if x.strip()]
        excluir = frozenset((i["tipo"], i["cultivo"], i.get("plaga")) for i in previas)
    salida = SUITES / args.salida
    if salida.exists() and not args.forzar:
        raise SystemExit(f"{salida} ya existe; usa --forzar para rehacerla")
    with AgeGraph.connect() as g:
        items = build(g, date.fromisoformat(args.fecha), seed=args.semilla, excluir=excluir,
                      fecha_conteos=date.fromisoformat(args.fecha_conteos) if args.fecha_conteos else None)
    if args.prefijo:
        items = [{**i, "qid": args.prefijo + i["qid"][1:]} for i in items]
    salida.write_text(
        "\n".join(json.dumps(i, ensure_ascii=False) for i in items) + "\n", encoding="utf-8")
    from collections import Counter
    print(json.dumps({"preguntas": len(items), "por_tipo": dict(Counter(i["tipo"] for i in items))}, ensure_ascii=False))


def cumplimiento_s1(args) -> None:
    """S1 answered by the local model with the exact core's tools or from memory (stage 5), scored as fixed in the plan.
    Short-paper modes (rules in pendientes/26, 24/11/2026): ``sin-guarda`` is the same agent without the guard, and
    ``rag`` is the conventional RAG baseline (V7 retrieval, same model, no tools)."""
    import statistics
    from collections import Counter

    from assistant.config import load_assistant_config
    from assistant.orchestration.agente import Agente
    from assistant.orchestration.tools import Herramientas
    from evaluation.compliance_answers import exacta, inventados
    from interfaces.jobs.vocabulary import load_vocabulary
    from knowledge.graph.age import AgeGraph
    from knowledge.normalization.ingredients import Aliases, spanish_names

    s1b = args.suite in ("s1b", "s1b2")
    archivo = {"s1b": "estructurada_genericas.jsonl", "s1b2": "estructurada_genericas_2.jsonl"}.get(args.suite,
                                                                                                    "estructurada.jsonl")
    items = [json.loads(line) for line in (SUITES / archivo).read_text(encoding="utf-8").splitlines() if line.strip()]
    if s1b:
        from evaluation.generic_suite import exacta as exacta_s1b
    if args.n:
        items = items[: args.n]
    local = load_assistant_config().generators.get("local", {})
    aliases = Aliases.load()
    gen = (f"_gen-{args.modelo.replace(':', '-')}" if args.modelo else "") + (
        "_guarda-salida" if args.modo == "herramientas" and not args.sin_guarda_salida else "") + (
        "_genericas" if args.genericas else "")
    run = RUNS / f"{datetime.now():%Y-%m-%d_%H%M}_cumplimiento_{args.suite}_{args.modo}{gen}"
    run.mkdir(parents=True, exist_ok=True)
    filas, ok, total = [], Counter(), Counter()
    base_url, modelo = local.get("base_url", "http://localhost:11434/v1"), args.modelo or local.get("model", "qwen3:8b")
    rag = _rag_convencional(base_url, modelo) if args.modo == "rag" else None
    with AgeGraph.connect() as g:
        h = (Herramientas(g, aliases, spanish_names(aliases), load_vocabulary())
             if args.modo in ("herramientas", "sin-guarda") else None)
        agente = Agente(base_url, modelo, h, guarda=args.modo != "sin-guarda",
                        guarda_valores=args.modo == "herramientas" and not args.sin_guarda_salida,
                        genericas=args.genericas)
        for it in items:
            hoy = __import__("datetime").date.fromisoformat(
                it.get("fecha") or (it.get("parametros") or {}).get("fecha", "2026-11-11"))
            if rag:
                rr = rag.responder(it["pregunta"])
                texto, llamadas, rondas, segundos, tokens = rr.texto, [], 1, rr.segundos, None
            else:
                r = agente.responder(it["pregunta"], hoy)
                texto, llamadas, rondas, segundos, tokens = r.texto, r.llamadas, r.rondas, r.segundos, r.tokens
            bien = exacta_s1b(it, texto) if s1b else exacta(it, texto)
            inv = inventados(texto, llamadas) if h else []
            total[it["tipo"]] += 1
            ok[it["tipo"]] += bien
            filas.append({"qid": it["qid"], "tipo": it["tipo"], "exacta": bien, "inventados": inv, "respuesta": texto,
                          "corregido": getattr(r, "corregido", []) if not rag else [],
                          "llamadas": llamadas, "rondas": rondas, "segundos": segundos, "tokens": tokens})
            print(f"{it['qid']} {it['tipo']:16} {'ok ' if bien else 'MAL'} {segundos:5.1f}s {texto[:90]!r}", flush=True)
    resumen = {"suite": archivo, "modo": args.modo, "modelo": modelo, "genericas": args.genericas,
               "preguntas": len(filas), "exactas": sum(ok.values()),
               "exactitud": round(sum(ok.values()) / len(filas), 3),
               "por_tipo": {t: round(ok[t] / total[t], 3) for t in total},
               "con_valor_inventado": sum(1 for f in filas if f["inventados"]),
               "sin_llamar_herramientas": sum(1 for f in filas if not f["llamadas"]) if h else None,
               "segundos_mediana": statistics.median(f["segundos"] for f in filas)}
    (run / "metricas.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    (run / "respuestas.jsonl").write_text("\n".join(json.dumps(f, ensure_ascii=False) for f in filas) + "\n", encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(prog="interfaces.jobs.evaluate")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("piloto-textual")
    p.add_argument("--por-documento", type=int, default=3)
    p.add_argument("--reusar", action="store_true")
    s = sub.add_parser("suite-estructurada", help="S1: preguntas con respuesta exacta desde el grafo")
    s.add_argument("--fecha", help="fecha de evaluación (ISO); por defecto hoy")
    st = sub.add_parser("suite-textual", help="S2: preguntas textuales (SENASA y UNALM), un tercio de varios saltos")
    st.add_argument("--un-salto", type=int, default=40)
    st.add_argument("--varios-saltos", type=int, default=20)
    st.add_argument("--generador", default="local")
    rs = sub.add_parser("recuperacion-s2", help="Recall@k, MRR y nDCG sobre S2 (léxico, denso e híbrido)")
    rs.add_argument("--firma")
    rs.add_argument("--ranking", nargs="+", default=["ts_rank", "idf"])
    js = sub.add_parser("juicios-s2", help="pool de fragmentos y juicios de relevancia 0/1/2 (juez Qwen)")
    js.add_argument("--profundidad", type=int, default=20)
    js.add_argument("--generador", default="local")
    js.add_argument("--firma")
    js.add_argument("--peso-genericas", type=float)
    js.add_argument("--descomponer", action="store_true", help="etapa 5: juzgar también lo que traen las subpreguntas")
    js.add_argument("--lista-grafo", type=float, help="etapa D3: juzgar también lo que trae la lista del grafo")
    js.add_argument("--salto-entidad", action="store_true", help="etapa D4: segundo salto por entidad")
    jm = sub.add_parser("juicios-muestra", help="Excel con una muestra estratificada para anotarla a mano")
    jm.add_argument("--n", type=int, default=180)
    jk = sub.add_parser("juicios-kappa", help="acuerdo entre la anotación manual y el juez (kappa de Cohen)")
    jk.add_argument("archivo")
    rj = sub.add_parser("recuperacion-juzgada", help="métricas graduadas sobre los juicios")
    rj.add_argument("--ranking", nargs="+", default=["idf", "ts_rank"])
    rj.add_argument("--firma")
    rj.add_argument("--peso-genericas", type=float, help="V4: factor para secciones genéricas (1 = sin cambio)")
    rj.add_argument("--encabezado-lexico", choices=["con", "sin", "peso"], help="V3b: encabezado en el índice léxico")
    rj.add_argument("--mmr", type=float, help="lambda de MMR (0.7 = sobre todo relevancia)")
    rj.add_argument("--particion", choices=["todo", "desarrollo", "prueba"], default="todo",
                    help="30 %% desarrollo / 70 %% prueba, estratificada por tipo (suites/particion_s2.json)")
    rj.add_argument("--expandir", choices=["si", "no"], help="etapa 4: sinónimos AGROVOC y SIGIA en la consulta léxica")
    rj.add_argument("--descomponer", action="store_true", help="etapa 5: subpreguntas (Qwen local) fundidas con RRF")
    rj.add_argument("--tope", type=int, help="etapa D1: máximo de fragmentos por documento (0 = sin tope)")
    rj.add_argument("--lista-grafo", type=float, help="etapa D3: peso de la lista del grafo en la fusión (0 = apagada)")
    rj.add_argument("--salto-entidad", action="store_true", help="etapa D4: segundo salto por entidad")
    cs = sub.add_parser("cumplimiento-s1", help="etapa 5: S1 respondida con las herramientas del núcleo exacto o de memoria")
    cs.add_argument("--modo", choices=["herramientas", "memoria", "sin-guarda", "rag"], required=True)
    cs.add_argument("--n", type=int, help="solo las primeras n preguntas (prueba)")
    cs.add_argument("--modelo", help="otro generador local (p. ej. gemma4:e4b); por defecto el de assistant.yaml")
    cs.add_argument("--sin-guarda-salida", action="store_true", help="sin la guarda de salida (como antes del 27/11)")
    cs.add_argument("--suite", choices=["s1", "s1b", "s1b2"], default="s1",
                    help="s1b: listas y conteos (herramientas genéricas); s1b2: la segunda, sin preguntas de la primera")
    cs.add_argument("--genericas", action="store_true", help="con productos_para_plaga e ingredientes_sin_limite")
    sub.add_parser("resumen-estadistico", help="Holm sobre las pruebas del paper e intervalos al 95 %% de sus estimaciones")
    rv = sub.add_parser("revision-preguntas", help="muestra de 20 preguntas de S2 para que la investigadora las revise")
    rv.add_argument("--forzar", action="store_true")
    sub.add_parser("revision-resultado", help="cuántas preguntas de la muestra revisada son válidas (Wilson 95 %%)")
    sb = sub.add_parser("suite-s1b", help="S1b: preguntas de listas y conteos desde el grafo (herramientas genéricas)")
    sb.add_argument("--fecha", default="2026-11-27", help="fecha de referencia de los LMR vigentes")
    sb.add_argument("--semilla", type=int, default=20261127)
    sb.add_argument("--salida", default="estructurada_genericas.jsonl")
    sb.add_argument("--excluir", help="suite anterior: sus plagas no se repiten")
    sb.add_argument("--fecha-conteos", help="fecha de los conteos de ingredientes sin LMR (se dice en la pregunta)")
    sb.add_argument("--prefijo", help="letra de los qid (g por defecto)")
    sb.add_argument("--forzar", action="store_true")
    fs = sub.add_parser("fidelidad-s2", help="OE3.I2: S2 respondida por el asistente local y fidelidad (RAGAS) con un juez local")
    fs.add_argument("--juez", default="qwen3:8b", help="modelo de Ollama que juzga cada oración")
    fs.add_argument("--n", type=int, help="solo las primeras n preguntas (prueba)")
    fs.add_argument("--sistema", choices=["agente", "rag"], default="agente", help="rag: línea base RAG convencional")
    fs.add_argument("--modelo", help="otro generador local (p. ej. gemma4:e4b); por defecto el de assistant.yaml")
    fs.add_argument("--verificador", help="etapa B: modelo que verifica cada oración (de otra familia que el generador)")
    fs.add_argument("--sin-guarda-salida", action="store_true", help="sin la guarda de salida (como antes del 27/11)")
    fs.add_argument("--por-partes", action="store_true", help="etapa D2: una búsqueda por cada parte de la pregunta")
    fs.add_argument("--lista-grafo", type=float, help="etapa D3: peso de la lista del grafo en la fusión")
    fs.add_argument("--salto-entidad", action="store_true", help="etapa D4: segundo salto por entidad")
    fs.add_argument("--particion", choices=["todo", "desarrollo", "prueba"], default="todo")
    rz = sub.add_parser("rejuzgar-s2", help="las mismas respuestas de una corrida de fidelidad, con otro juez")
    rz.add_argument("--corrida", required=True, help="corrida de fidelidad-s2 con oraciones y evidencia")
    rz.add_argument("--juez", required=True, help="modelo de Ollama de otra familia (gemma4:e4b, llama3.1:8b)")
    rp = sub.add_parser("repetibilidad-s2", help="cada pregunta de S2 respondida varias veces: ¿sale igual?")
    rp.add_argument("--temperatura", type=float, default=0.0)
    rp.add_argument("--semilla", type=int, default=20261127, help="-1 = sin semilla fija")
    rp.add_argument("--repeticiones", type=int, default=2)
    rp.add_argument("--modelo", help="generador local (por defecto el de assistant.yaml)")
    rp.add_argument("--particion", choices=["todo", "desarrollo", "prueba"], default="todo")
    rp.add_argument("--n", type=int, default=0)
    fm = sub.add_parser("fidelidad-muestra", help="Excel con oraciones de S2 para la anotación humana de fidelidad")
    fm.add_argument("--corrida", required=True)
    fm.add_argument("--n", type=int, default=30, help="respuestas: todas las de varios saltos y el resto de un salto")
    fa = sub.add_parser("fidelidad-acuerdo", help="acuerdo entre jueces y con la anotación humana; análisis de errores")
    fa.add_argument("--corrida", required=True, help="corrida de fidelidad-s2 (juez del generador)")
    fa.add_argument("--jueces", nargs="*", default=[], help="corridas de rejuzgar-s2 sobre esa corrida")
    fa.add_argument("--anotacion", help="Excel anotado (fidelidad_s2_muestra_anotacion.xlsx)")
    mv = sub.add_parser("fidelidad-muestra-verificacion",
                        help="Excel para anotar las respuestas con la verificación por oraciones (etapa B)")
    mv.add_argument("--base", default="2026-11-26_2015_fidelidad_s2_qwen3-8b", help="corrida anotada el 26/11")
    mv.add_argument("--corridas", nargs="+", default=["2026-11-27_0042_fidelidad_s2_ver-gemma4-e4b_qwen3-8b",
                                                      "2026-11-27_0120_fidelidad_s2_gen-gemma4-e4b_ver-qwen3-8b_qwen3-8b"])
    mv.add_argument("--forzar", action="store_true", help="rehace el Excel aunque exista")
    av = sub.add_parser("fidelidad-acuerdo-verificacion",
                        help="la verificación por oraciones medida con la anotación de la persona (antes y después)")
    av.add_argument("--anotacion", help="Excel anotado (por defecto fidelidad_s2_verificacion_anotacion.xlsx)")
    jr = sub.add_parser("juicios-rejuez", help="los 180 juicios de relevancia anotados, con un juez de otra familia")
    jr.add_argument("archivo", help="Excel anotado de la muestra de relevancia")
    jr.add_argument("--juez", required=True)
    au = sub.add_parser("analisis-u1", help="por qué el híbrido tiene menor útil@1 que el denso (origen del primer pasaje)")
    au.add_argument("--firma", help="índice (por defecto el configurado)")
    vr = sub.add_parser("validar-reales", help="S3: programas reales de las tesis (resolución de filas y hallazgos)")
    vr.set_defaults(_=None)
    ir = sub.add_parser("importar-reales", help="etapa E: los programas reales como hojas de campo por el camino del sistema")
    ir.add_argument("--contra", default="2026-11-27_0405_validador_reales", help="corrida de validar-reales que reproducir")
    ir.add_argument("--rehacer-hojas", action="store_true", help="vuelve a escribir las hojas desde programas_reales.json")
    vc = sub.add_parser("validar-controles", help="S3: programas limpios y casi incumplimientos en los bordes de las reglas")
    vc.add_argument("--n", type=int, default=42)
    ra = sub.add_parser("reales-acuerdo", help="hallazgos del validador frente a la referencia fijada a mano")
    ra.add_argument("--corrida", required=True, help="corrida de validar-reales")
    ra.add_argument("--adjudicada", action="store_true",
                    help="aplica programas_reales_adjudicacion.json (filas resueltas contra la fuente oficial)")
    cd = sub.add_parser("cobertura-documentos", help="etapa D: documentos de referencia entre los pasajes que lee el generador")
    cd.add_argument("--particion", choices=["todo", "desarrollo", "prueba"], default="desarrollo")
    cd.add_argument("--k", type=int, default=6, help="pasajes que lee el generador")
    cd.add_argument("--tope", type=int, help="máximo de fragmentos por documento (0 = sin tope)")
    cd.add_argument("--lista-grafo", type=float, help="etapa D3: peso de la lista del grafo en la fusión (0 = apagada)")
    cd.add_argument("--salto-entidad", action="store_true", help="etapa D4: segundo salto por entidad")
    sv = sub.add_parser("sin-verificar", help="etapa A desde una corrida de la etapa B: respuestas antes de verificar")
    sv.add_argument("--corrida", required=True)
    cr = sub.add_parser("comparar-recuperacion", help="pruebas pareadas entre recuperadores de una corrida")
    cr.add_argument("--corrida", required=True, help="corrida de recuperacion-juzgada con por_pregunta.jsonl")
    vl = sub.add_parser("validar-llm", help="S3: el mismo modelo sin núcleo exacto revisa los programas (línea base)")
    vl.add_argument("--modelo", help="por defecto el generador de assistant.yaml")
    vl.add_argument("--solo-controles", action="store_true", help="solo los 42 controles (sin la suite sembrada)")
    co = sub.add_parser("comparar", help="comparaciones pareadas (McNemar en S1, Wilcoxon en S2) entre corridas")
    co.add_argument("--s1", required=True, help="corrida de S1 del sistema completo")
    co.add_argument("--s1-contra", nargs="+", default=[], help="corridas de S1 contra las que se compara")
    co.add_argument("--s2", help="corrida de fidelidad en S2 del sistema completo")
    co.add_argument("--s2-contra", help="corrida de fidelidad en S2 de la línea base")
    vs = sub.add_parser("validar-s3", help="S3: el validador sobre los programas con incumplimientos sembrados")
    vs.set_defaults(_=None)
    sp = sub.add_parser("suite-programas", help="S3: programas con incumplimientos sembrados")
    sp.add_argument("--n", type=int, default=30)
    args = parser.parse_args()
    {"piloto-textual": piloto_textual, "suite-estructurada": suite_estructurada,
     "suite-programas": suite_programas, "suite-textual": suite_textual,
     "recuperacion-s2": recuperacion_s2, "juicios-s2": juicios_s2, "juicios-muestra": juicios_muestra,
     "juicios-kappa": juicios_kappa, "recuperacion-juzgada": recuperacion_juzgada,
     "cumplimiento-s1": cumplimiento_s1, "fidelidad-s2": fidelidad_s2,
     "validar-s3": validar_s3, "comparar": comparar, "rejuzgar-s2": rejuzgar_s2,
     "repetibilidad-s2": repetibilidad_s2, "suite-s1b": suite_s1b,
     "revision-preguntas": revision_preguntas, "revision-resultado": revision_resultado,
     "resumen-estadistico": resumen_estadistico,
     "fidelidad-muestra": fidelidad_muestra, "fidelidad-acuerdo": fidelidad_acuerdo,
     "fidelidad-muestra-verificacion": fidelidad_muestra_verificacion,
     "fidelidad-acuerdo-verificacion": fidelidad_acuerdo_verificacion,
     "juicios-rejuez": juicios_rejuez, "analisis-u1": analisis_u1,
     "validar-reales": validar_reales, "reales-acuerdo": reales_acuerdo, "importar-reales": importar_reales,
     "validar-controles": validar_controles,
     "comparar-recuperacion": comparar_recuperacion, "sin-verificar": sin_verificar,
     "cobertura-documentos": cobertura_documentos, "validar-llm": validar_llm}[args.command](args)


if __name__ == "__main__":
    main()
