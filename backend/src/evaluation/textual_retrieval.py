"""Retrieval metrics on suite S2 (Recall@1/5/10, MRR@10, nDCG@10) for the lexical, dense and hybrid lists.

A retrieved fragment satisfies an evidence when it comes from the same document and contains its literal span (or most
of its content words; see ``textual_suite.relevant``). Nothing depends on chunk ids, so every chunking variant of stage
3 is measured against the same suite. For a multi-hop question, Recall@k is the share of its evidences found in the top
k; MRR takes the first fragment that satisfies any of them; nDCG uses binary gains, one per evidence covered."""
from __future__ import annotations

import math
import statistics

from .textual_suite import relevant

KS = (1, 5, 10)


def _fragments(conn, signature: str, ids: list[str]) -> dict[str, tuple[str, str]]:
    rows = conn.execute("SELECT chunk_id, doc_id, texto FROM fragmentos WHERE firma = %s AND chunk_id = ANY(%s)",
                        (signature, ids)).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


def score_list(ranked: list[str], frags: dict[str, tuple[str, str]], evidences: list[dict]) -> dict[str, float]:
    covered_at: dict[int, int] = {}        # evidence index -> first rank that covers it
    first_hit = None
    gains = []
    for rank, cid in enumerate(ranked[:10], start=1):
        doc, text = frags.get(cid, ("", ""))
        new = [i for i, ev in enumerate(evidences) if i not in covered_at and doc == ev["doc_id"] and relevant(text, ev)]
        hit_any = any(doc == ev["doc_id"] and relevant(text, ev) for ev in evidences)
        if hit_any and first_hit is None:
            first_hit = rank
        for i in new:
            covered_at[i] = rank
        gains.append(1.0 if new else 0.0)
    out = {f"recall@{k}": sum(1 for r in covered_at.values() if r <= k) / len(evidences) for k in KS}
    out["mrr@10"] = 1 / first_hit if first_hit else 0.0
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
    idcg = sum(1 / math.log2(i + 2) for i in range(min(len(evidences), 10)))
    out["ndcg@10"] = dcg / idcg
    return out


def evaluate(conn, retriever, items: list[dict]) -> tuple[dict, list[dict]]:
    """``retriever`` is a HybridRetriever with top_k >= 10. Returns averages per list (and per question type) and the
    per-question records."""
    sig = retriever.signature
    records = []
    for it in items:
        q = it["pregunta"]
        lex = retriever.lexical(q)[:10]
        den = [c for c, _ in retriever.dense(q)][:10]
        hyb = [p.chunk_id for p in retriever.retrieve(q)][:10]
        frags = _fragments(conn, sig, list({*lex, *den, *hyb}))
        records.append({"qid": it["qid"], "tipo": it["tipo"],
                        **{name: score_list(lst, frags, it["evidencias"])
                           for name, lst in (("lexico", lex), ("denso", den), ("hibrido", hyb))}})

    def mean(recs, name):
        keys = recs[0][name].keys()
        return {k: round(statistics.fmean(r[name][k] for r in recs), 3) for k in keys}

    summary = {"n": len(records)}
    for name in ("lexico", "denso", "hibrido"):
        summary[name] = mean(records, name)
        summary[name]["por_tipo"] = {t: mean([r for r in records if r["tipo"] == t], name)
                                     for t in sorted({r["tipo"] for r in records})}
    return summary, records
