"""Pilot of the textual suite on the indexed corpus: synthetic questions with a known source chunk, retrieval metrics
per retriever, and end-to-end answers with the configured generator.

Building the pilot set (``build_pilot``): chunks are sampled per document (stratified, fixed seed) among those with
enough prose; a language model writes one question in Spanish that only that chunk answers, plus a short reference
answer. The source chunk is the relevant one (strict); the same document and section count as lenient. Out-of-scope
questions (other crops, residue limits asked as text) test abstention. This is a pilot, not the protocol suite: the
protocol's 50 textual questions get human relevance judgments; these do not.

Running it (``run_pilot``):
- retrieval with three retrievers on the same index: lexical only, dense only (base BGE-M3), hybrid (RRF): Recall@1,
  @5, @10 and MRR@10, strict and lenient;
- end to end with the configured answerer: answered with evidence, cited, the source chunk among the cited passages,
  abstention on out-of-scope questions, latency, and faithfulness judged by a model (share of the answer's statements
  supported by the cited passages; one judge here, the protocol's two-judge panel later).
"""
from __future__ import annotations

import json
import random
import re
import statistics
import time
from dataclasses import asdict, dataclass, field

from assistant.answer import Answerer
from assistant.retrieval.search import HybridRetriever

QUESTION_SYSTEM = """Eres un evaluador. Recibes un pasaje de un documento técnico agrícola. Escribe UNA pregunta en
español que un técnico de campo haría y que este pasaje responde de forma específica (no una pregunta general que
muchos documentos responderían). No copies frases textuales del pasaje en la pregunta. Devuelve solo JSON:
{"pregunta": "...", "respuesta_referencia": "..."} con una respuesta de una o dos oraciones basada en el pasaje."""

JUDGE_SYSTEM = """Eres un juez de fidelidad. Recibes una respuesta y los pasajes que cita. Divide la respuesta en
afirmaciones y cuenta cuántas están respaldadas por los pasajes. Devuelve solo JSON:
{"afirmaciones": n, "respaldadas": m}"""

OUT_OF_SCOPE = [
    "¿Cuál es el límite máximo de residuos de clorpirifos en arándano para la Unión Europea?",
    "¿Cómo se controla la sigatoka negra en banano orgánico?",
    "¿Qué variedades de cacao son tolerantes a la moniliasis en San Martín?",
    "¿Cuál es el precio internacional de la palta Hass en 2026?",
    "¿Qué dosis de glifosato se recomienda para malezas en caña de azúcar?",
    "¿Cuántos días de carencia tiene el producto ADIKO SC en arándano?",
]


@dataclass
class PilotItem:
    qid: str
    question: str
    reference: str
    chunk_id: str
    doc_id: str
    section: list[str]
    in_scope: bool = True


def _json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return json.loads(m.group(0)) if m else {}


def build_pilot(conn, signature: str, generator, per_doc: int = 3, seed: int = 20261106,
                min_tokens: int = 120) -> list[PilotItem]:
    rows = conn.execute(
        """SELECT chunk_id, doc_id, seccion, texto FROM fragmentos
           WHERE firma = %s AND rol <> 'parent' AND tokens >= %s AND NOT ('table' = ANY(tipos))
           ORDER BY doc_id, orden""", (signature, min_tokens)).fetchall()
    by_doc: dict[str, list] = {}
    for r in rows:
        by_doc.setdefault(r[1], []).append(r)
    rng = random.Random(seed)
    items: list[PilotItem] = []
    for doc_id in sorted(by_doc):
        chunks = by_doc[doc_id]
        for r in rng.sample(chunks, min(per_doc, len(chunks))):
            out = _json(generator.generate(QUESTION_SYSTEM, f"Pasaje:\n{r[3]}").text)
            if out.get("pregunta"):
                items.append(PilotItem(f"q{len(items) + 1:03d}", out["pregunta"].strip(),
                                       out.get("respuesta_referencia", "").strip(), r[0], r[1], list(r[2] or [])))
    for k, q in enumerate(OUT_OF_SCOPE, start=1):
        items.append(PilotItem(f"o{k:03d}", q, "", "", "", [], in_scope=False))
    return items


# retrieval -----------------------------------------------------------------------------------------------------------

def _ranked_ids(retriever: HybridRetriever, mode: str, question: str, k: int) -> list[str]:
    if mode == "lexical":
        return retriever.lexical(question)[:k]
    if mode == "dense":
        return [cid for cid, _ in retriever.dense(question)][:k]
    keep = retriever.top_k
    retriever.top_k = k
    try:
        return [p.chunk_id for p in retriever.retrieve(question)]
    finally:
        retriever.top_k = keep


def retrieval_metrics(conn, retriever: HybridRetriever, items: list[PilotItem], k: int = 10) -> dict:
    meta = {r[0]: (r[1], tuple(r[2] or [])) for r in conn.execute(
        "SELECT chunk_id, doc_id, seccion FROM fragmentos WHERE firma = %s", (retriever.signature,)).fetchall()}
    out = {}
    for mode in ("lexical", "dense", "hybrid"):
        strict = {"r1": [], "r5": [], "r10": [], "mrr": []}
        lenient = {"r1": [], "r5": [], "r10": [], "mrr": []}
        for it in (i for i in items if i.in_scope):
            ranked = _ranked_ids(retriever, mode, it.question, k)
            target = (it.doc_id, tuple(it.section))
            for store, hit in ((strict, lambda c, cid=it.chunk_id: c == cid),
                               (lenient, lambda c, t=target: meta.get(c) == t)):
                pos = next((i for i, c in enumerate(ranked, start=1) if hit(c)), None)
                store["r1"].append(int(pos is not None and pos <= 1))
                store["r5"].append(int(pos is not None and pos <= 5))
                store["r10"].append(int(pos is not None and pos <= 10))
                store["mrr"].append(1 / pos if pos else 0.0)
        out[mode] = {"strict": {m: round(statistics.mean(v), 3) for m, v in strict.items()},
                     "lenient": {m: round(statistics.mean(v), 3) for m, v in lenient.items()}}
    return out


# end to end ----------------------------------------------------------------------------------------------------------

@dataclass
class AnswerRecord:
    qid: str
    in_scope: bool
    evidence: bool
    cited: bool
    source_cited: bool
    seconds: float
    faithful: float | None
    answer: str = field(repr=False, default="")


def end_to_end(answerer: Answerer, judge, items: list[PilotItem]) -> tuple[dict, list[AnswerRecord]]:
    records = []
    for it in items:
        t0 = time.perf_counter()
        res = answerer.answer(it.question)
        secs = round(time.perf_counter() - t0, 2)
        cited_ids = {c.chunk_id for c in res.citations}
        faithful = None
        if res.evidence and res.citations:
            passages = "\n\n".join(f"[{c.n}] {c.text}" for c in res.citations)
            j = _json(judge.generate(JUDGE_SYSTEM, f"Respuesta:\n{res.text}\n\nPasajes citados:\n{passages}").text)
            if j.get("afirmaciones"):
                faithful = round(min(1.0, j.get("respaldadas", 0) / j["afirmaciones"]), 3)
        records.append(AnswerRecord(it.qid, it.in_scope, res.evidence, bool(res.citations),
                                    it.chunk_id in cited_ids, secs, faithful, res.text))
    ins = [r for r in records if r.in_scope]
    outs = [r for r in records if not r.in_scope]
    faith = [r.faithful for r in ins if r.faithful is not None]
    summary = {
        "in_scope": len(ins), "out_of_scope": len(outs),
        "answered_with_evidence": round(sum(r.evidence for r in ins) / len(ins), 3) if ins else None,
        "cited_when_answered": round(sum(r.cited for r in ins if r.evidence) / max(1, sum(r.evidence for r in ins)), 3),
        "source_chunk_cited": round(sum(r.source_cited for r in ins) / len(ins), 3) if ins else None,
        "abstained_out_of_scope": round(sum(not r.evidence for r in outs) / len(outs), 3) if outs else None,
        "faithfulness_mean": round(statistics.mean(faith), 3) if faith else None,
        "faithfulness_n": len(faith),
        "latency_median_s": round(statistics.median(r.seconds for r in records), 2) if records else None,
        "latency_p90_s": round(sorted(r.seconds for r in records)[int(0.9 * (len(records) - 1))], 2) if records else None,
    }
    return summary, records


def as_rows(items) -> list[dict]:
    return [asdict(i) for i in items]
