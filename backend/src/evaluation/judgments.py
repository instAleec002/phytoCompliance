"""Graded relevance judgments for suite S2 (protocol of Objetivo 2, change approved by the author on 11/11/2026).

Pool: for each question, the union of the top ``depth`` fragments of every retriever configuration (lexical with idf,
lexical without idf, dense BGE-M3 and the hybrid fusion; new configurations add their own lists later). Grades:
0 = not relevant, 1 = partly relevant, 2 = answers the question. The page a question was built from counts as grade 2
without the judge. The rest is graded by Qwen3-8B, validated against a manually annotated sample (Cohen's kappa): on 23/11/2026,
with n = 180, kappa 0.667 for relevant yes/no (accepted: primary metrics) and 0.483 for the 0/1/2 scale (secondary
metrics, reported with that kappa); the result is kept in ml/evaluation/suites/juicios_s2_kappa.json.

Judgments are stored with document, pages and text, not just chunk ids, so a fragment of another chunking (stage 3)
inherits the grade of a judged fragment of the same document when they overlap; whatever stays unjudged can be judged
incrementally with the same judge, so every chunking variant is compared on the same footing."""
from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
from pathlib import Path

from knowledge.vocabulary.agrovoc import norm

from .textual_suite import _json, relevant

JUDGE = """Eres un evaluador de búsqueda. Recibes una pregunta de un técnico de sanidad vegetal o de un exportador
agrícola peruano y un fragmento de un documento. Califica el fragmento:
2 = contiene la respuesta a la pregunta (completa o casi completa);
1 = relevante en parte: trata el mismo tema concreto y aporta parte de la respuesta o un dato necesario;
0 = no ayuda a responder (otro tema, o el mismo tema general sin el dato que se pide).
Juzga solo lo que dice el fragmento, sin tu propio conocimiento. Responde solo JSON: {"grado": 0|1|2}"""


def text_hash(text: str) -> str:
    return hashlib.sha1(norm(text).encode("utf-8")).hexdigest()[:16]


class Judgments:
    """judgments file: one JSON per line {qid, doc_id, paginas, hash, texto, grado, fuente, firma, chunk_id}."""

    def __init__(self, path: Path):
        self.path = path
        self.rows: list[dict] = []
        if path.exists():
            self.rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self._by_key = {(r["qid"], r["hash"]): r for r in self.rows}

    def add(self, row: dict) -> None:
        self.rows.append(row)
        self._by_key[(row["qid"], row["hash"])] = row
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def grade(self, qid: str, doc_id: str, pages: list[int], text: str) -> int | None:
        """Exact match by text, else inherited from an overlapping judged fragment of the same document."""
        exact = self._by_key.get((qid, text_hash(text)))
        if exact:
            return exact["grado"]
        words = {w for w in norm(text).split() if len(w) > 3}
        best = None
        for r in self.rows:
            if r["qid"] != qid or r["doc_id"] != doc_id or not set(r["paginas"]) & set(pages):
                continue
            other = {w for w in norm(r["texto"]).split() if len(w) > 3}
            if words and len(words & other) / len(words) >= 0.6:
                best = max(best or 0, r["grado"])
        return best


def pool(conn, retrievers: dict, question: str, depth: int = 20) -> list[str]:
    ids: list[str] = []
    for r in retrievers.values():
        for cid in [*r.lexical(question)[:depth], *[c for c, _ in r.dense(question)[:depth]],
                    *[p.chunk_id for p in r.retrieve(question)][:depth]]:
            if cid not in ids:
                ids.append(cid)
    return ids


def fragments(conn, signature: str, ids: list[str]) -> dict[str, dict]:
    rows = conn.execute(
        """SELECT f.chunk_id, f.doc_id, f.paginas, f.texto, d.titulo FROM fragmentos f JOIN documentos d ON d.doc_id = f.doc_id
           WHERE f.firma = %s AND f.chunk_id = ANY(%s)""", (signature, ids)).fetchall()
    return {r[0]: {"doc_id": r[1], "paginas": list(r[2] or []), "texto": r[3], "titulo": r[4]} for r in rows}


def judge_pool(conn, retrievers: dict, items: list[dict], judge, store: Judgments, depth: int = 20, log=print) -> dict:
    signature = next(iter(retrievers.values())).signature
    stats = {"juzgados": 0, "por_fragmento": 0, "heredados": 0, "ya_estaban": 0}
    for n, it in enumerate(items, start=1):
        ids = pool(conn, retrievers, it["pregunta"], depth)
        frs = fragments(conn, signature, ids)
        for cid in ids:
            f = frs[cid]
            h = text_hash(f["texto"])
            if (it["qid"], h) in store._by_key:
                stats["ya_estaban"] += 1
                continue
            base = {"qid": it["qid"], "doc_id": f["doc_id"], "paginas": f["paginas"], "hash": h, "texto": f["texto"],
                    "firma": signature, "chunk_id": cid}
            if any(f["doc_id"] == ev["doc_id"] and relevant(f["texto"], ev) for ev in it["evidencias"]):
                store.add({**base, "grado": 2, "fuente": "fragmento"})
                stats["por_fragmento"] += 1
                continue
            inherited = store.grade(it["qid"], f["doc_id"], f["paginas"], f["texto"])
            if inherited is not None:
                store.add({**base, "grado": inherited, "fuente": "heredado"})
                stats["heredados"] += 1
                continue
            d = _json(judge.generate(JUDGE, f"Pregunta: {it['pregunta']}\n\nFragmento de «{f['titulo']}», "
                                            f"p. {', '.join(map(str, f['paginas']))}:\n{f['texto'][:2500]}").text)
            g = d.get("grado")
            g = int(g) if str(g) in ("0", "1", "2") else 0
            store.add({**base, "grado": g, "fuente": "juez"})
            stats["juzgados"] += 1
        if n % 5 == 0:
            log(f"{n}/{len(items)} preguntas, {stats}")
    return stats


# metrics over graded judgments (definitions of the protocol); ranx cross-checks them in the final evaluation
def graded_metrics(ranked: list[tuple[str, list[int], str]], qid: str, store: Judgments, ks=(1, 5, 10)) -> dict:
    """``ranked``: (doc_id, pages, text) in rank order. Unjudged fragments count as 0."""
    grades = [store.grade(qid, d, p, t) or 0 for d, p, t in ranked[:max(ks)]]
    judged = [r["grado"] for r in store.rows if r["qid"] == qid]
    n_rel = sum(1 for g in judged if g >= 1)
    out = {}
    for k in ks:
        out[f"recall@{k}"] = (sum(1 for g in grades[:k] if g >= 1) / n_rel) if n_rel else 0.0
        out[f"util@{k}"] = 1.0 if any(g == 2 for g in grades[:k]) else 0.0          # at least one answering fragment
    first = next((i for i, g in enumerate(grades[:10], start=1) if g >= 1), None)
    out["mrr@10"] = 1 / first if first else 0.0
    dcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(grades[:10]))
    ideal = sorted(judged, reverse=True)[:10]
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    out["ndcg@10"] = dcg / idcg if idcg else 0.0
    return out


def sample_for_annotation(store: Judgments, questions: dict[str, str], titles: dict[str, str], out: Path,
                          n: int = 180, seed: int = 20261111) -> int:
    """Judge-graded rows only, stratified by the judge's grade (so the rare 2s are represented), grade hidden."""
    rng = random.Random(seed)
    rows = [r for r in store.rows if r["fuente"] == "juez"]
    by = {g: [r for r in rows if r["grado"] == g] for g in (0, 1, 2)}
    take = []
    for rs in by.values():
        take += rng.sample(rs, min(len(rs), n // 3))
    rest = [r for r in rows if r not in take]
    take += rng.sample(rest, min(len(rest), n - len(take)))
    # grouped by question (reading one question's fragments together is faster); order inside a group is random,
    # so the judge's ranking does not leak through the order
    rng.shuffle(take)
    take.sort(key=lambda r: r["qid"])
    _write_sheet(take, questions, titles, out)
    return len(take)


GRADE_COL = "Tu grado"


def _write_sheet(rows: list[dict], questions: dict[str, str], titles: dict[str, str], out: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = "Anotar"
    head = ["N.°", "Pregunta", "Documento", "Pág.", "Fragmento", GRADE_COL, "id"]
    ws.append(head)
    widths = [6, 38, 28, 7, 95, 10, 4]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[chr(64 + i)].width = w
    ws.column_dimensions["G"].hidden = True
    bold, wrap = Font(bold=True, color="FFFFFF"), Alignment(wrap_text=True, vertical="top")
    for c in ws[1]:
        c.font, c.fill, c.alignment = bold, PatternFill("solid", fgColor="2F5D50"), Alignment(vertical="center")
    fills = [PatternFill("solid", fgColor="FFFFFF"), PatternFill("solid", fgColor="EEF4F1")]
    grade_fill = PatternFill("solid", fgColor="FFF6D5")
    top = Border(top=Side(style="medium", color="2F5D50"))
    group, prev = -1, None
    for n, r in enumerate(rows, start=1):
        first = r["qid"] != prev
        if first:
            group += 1
        prev = r["qid"]
        text = " ".join(r["texto"].split())[:1500]
        ws.append([n, questions[r["qid"]] if first else "↑ misma pregunta", titles.get(r["doc_id"], r["doc_id"]),
                   ", ".join(map(str, r["paginas"])), text, None, f"{r['qid']}:{r['hash']}"])
        row = ws.max_row
        for c in ws[row]:
            c.alignment, c.fill = wrap, fills[group % 2]
            if first:
                c.border = top
        ws.cell(row, 2).font = Font(bold=first, color="000000" if first else "888888")
        ws.cell(row, 6).fill = grade_fill
        ws.cell(row, 6).alignment = Alignment(horizontal="center", vertical="top")
        lines = max(len(text) / 105, len(questions[r["qid"]]) / 40 if first else 1, len(ws.cell(row, 3).value) / 30)
        ws.row_dimensions[row].height = min(409, 15 * (int(lines) + 1))
    dv = DataValidation(type="list", formula1='"0,1,2"', allow_blank=True, showErrorMessage=True,
                        errorTitle="Grado", error="Escribe 0, 1 o 2")
    ws.add_data_validation(dv)
    dv.add(f"F2:F{ws.max_row}")
    ws.freeze_panes = "B2"

    guide = wb.create_sheet("Cómo calificar")
    for line in [
        ["Grado", "Cuándo"],
        [2, "El fragmento contiene la respuesta a la pregunta (completa o casi completa)."],
        [1, "Trata el mismo tema concreto y aporta parte de la respuesta o un dato necesario."],
        [0, "No ayuda: otro tema, o el mismo tema general sin el dato que se pide."],
        [],
        ["", "Juzga solo lo que dice el fragmento, no lo que tú sabes del tema."],
        ["", "No importa de qué documento venga: si responde, es 2 aunque la pregunta se haya hecho desde otro."],
        ["", "Las filas con fondo alterno agrupan los fragmentos de una misma pregunta."],
        ["", "Puedes dejar filas en blanco: solo cuentan las que califiques."],
    ]:
        guide.append(line)
    guide.column_dimensions["A"].width, guide.column_dimensions["B"].width = 8, 100
    guide["A1"].font = guide["B1"].font = Font(bold=True)
    wb.move_sheet("Cómo calificar", offset=-1)
    wb.active = 1
    wb.save(out)


KAPPA_MIN = 0.6   # protocol of Objetivo 2: the judge's labels are accepted with Cohen's kappa of at least 0.6


def cohen_kappa(a: list[int], b: list[int]) -> float:
    n = len(a)
    labels = sorted(set(a) | set(b))
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in labels)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def agreement(store: Judgments, annotated: Path) -> dict:
    by_id = {f"{r['qid']}:{r['hash']}": r["grado"] for r in store.rows}
    from openpyxl import load_workbook

    hers, judge = [], []
    ws = load_workbook(annotated, read_only=True)["Anotar"]
    rows = ws.iter_rows(values_only=True)
    head = list(next(rows))
    gi, ii = head.index(GRADE_COL), head.index("id")
    for row in rows:
        g = str(row[gi]).strip().removesuffix(".0") if row[gi] is not None else ""
        if g in ("0", "1", "2") and row[ii] in by_id:
            hers.append(int(g))
            judge.append(by_id[row[ii]])
    if not hers:
        return {"n": 0}
    binary = cohen_kappa([int(x >= 1) for x in hers], [int(x >= 1) for x in judge])
    graded = cohen_kappa(hers, judge)
    # Decision of 23/11/2026 (author): the judge is accepted per scale. Yes/no relevance (grade >= 1) feeds the
    # primary metrics (Recall@k, MRR@10); the 0/1/2 scale feeds the secondary ones (nDCG@10, util@k), reported
    # with their kappa when it stays below the threshold.
    return {"n": len(hers), "kappa_0_1_2": round(graded, 3), "kappa_relevante_si_no": round(binary, 3),
            "acuerdo_exacto": round(statistics.fmean(x == y for x, y in zip(hers, judge)), 3),
            "acepta_relevancia_si_no": binary >= KAPPA_MIN, "acepta_grados_0_1_2": graded >= KAPPA_MIN,
            "metricas_principales": "recall@k, mrr@10 (relevancia sí/no)" if binary >= KAPPA_MIN else "solo página de origen",
            "metricas_secundarias": "ndcg@10, util@k (grados 0/1/2)" + ("" if graded >= KAPPA_MIN else f", con kappa {graded:.3f} < {KAPPA_MIN}")}
