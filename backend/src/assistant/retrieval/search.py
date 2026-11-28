"""Hybrid retrieval over the corpus: lexical (PostgreSQL full text with Spanish stemming) and dense (pgvector,
cosine), fused by reciprocal rank (RRF, k = 60). Searches one pipeline signature and one embedding model, so results
never mix chunkings. A child chunk (``parent_child`` chunker) brings its parent's text as context.

Lexical matching uses OR between the query terms (``plainto_tsquery`` joins them with AND, which in natural questions
leaves almost nothing); ranking (``ts_rank_cd``) still prefers passages that contain more of them. It is the BM25
stand-in of this stack: PostgreSQL has no BM25 without an extension."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import psycopg

from knowledge.corpus.store import vector_literal
from knowledge.documents.chunkers.structural import is_generic

from .embeddings import Embedder


@dataclass
class Passage:
    chunk_id: str
    doc_id: str
    title: str
    source: str
    level: str
    url: str
    section: list[str]
    pages: list[int]
    text: str
    header: str
    score: float
    lexical_rank: int | None = None
    dense_rank: int | None = None
    dense_score: float | None = None
    context: str = field(default="", repr=False)       # parent text when the hit is a child chunk


def latest_signature(conn: psycopg.Connection, model: str) -> str | None:
    row = conn.execute("SELECT firma FROM indexaciones WHERE modelo = %s ORDER BY creada DESC LIMIT 1", (model,)).fetchone()
    return row[0] if row else None


class HybridRetriever:
    def __init__(self, conn: psycopg.Connection, embedder: Embedder, signature: str, k_lexical: int = 30,
                 k_dense: int = 30, rrf_k: int = 60, top_k: int = 6, min_dense_score: float = 0.45,
                 lexical_weight: float = 1.0, dense_weight: float = 1.0, vocabulary=None,
                 lexical_ranking: str = "ts_rank", generic_weight: float = 1.0, lexical_header: str = "con",
                 mmr_lambda: float | None = None, neighbors: int = 0, max_per_document: int | None = None,
                 graph_list_weight: float | None = None, graph_vocabulary=None, graph_list_k: int = 10,
                 entity_hop: bool = False, hop_k: int = 6):
        self.lexical_ranking = lexical_ranking            # ts_rank (no idf) | idf (BM25-style term weights)
        self.conn, self.embedder, self.signature = conn, embedder, signature
        self.k_lexical, self.k_dense, self.rrf_k, self.top_k = k_lexical, k_dense, rrf_k, top_k
        self.min_dense_score = min_dense_score
        # weighted RRF: the pilot of 06/11/2026 showed the lexical list pushing good dense hits out of the top 5
        self.lexical_weight, self.dense_weight = lexical_weight, dense_weight
        # controlled vocabulary (stage 4): the lexical query also searches the synonyms of the terms the question names
        self.vocabulary = vocabulary
        # V4 (stage 3): fragments from generic sections (abstract, introduction, conclusions…) keep their place in the
        # index and can be cited, but their fused score is multiplied by this factor (1.0 = off)
        self.generic_weight = generic_weight
        # V3b: the lexical index has the header (title and section) in every fragment, so a word of the title matches
        # all of them alike. «con» = as stored; «sin» = text only; «peso» = header at weight D (0.1), text at A (1.0).
        # Computed at query time (no schema change): slower, meant for measuring before changing the index.
        if lexical_header not in ("con", "sin", "peso"):
            raise ValueError(f"lexical_header desconocido: {lexical_header!r}")
        self.lexical_header = lexical_header
        # MMR: reorders the final candidates trading relevance against similarity to the ones already chosen, so two
        # near-copies (theses repeat paragraphs) do not take two places. None = off; 0.7 = mostly relevance.
        self.mmr_lambda = mmr_lambda
        # neighbors: the generator also reads the previous and next fragments of the same section (answers that cross a
        # fragment's edge); retrieval and citations stay on the hit itself. 0 = off.
        self.neighbors = neighbors
        # D1 (27/11/2026): at most this many fragments of one document among the candidates, so that a multi-hop
        # question can bring its second document into the passages the generator reads. None = off.
        self.max_per_document = max_per_document
        # D3 (27/11/2026): a third list in the fusion, the fragments that name the graph terms of the question, one
        # per document (multi-hop questions turn on one entity seen by two documents). None = off.
        self.graph_list_weight, self.graph_vocabulary, self.graph_list_k = graph_list_weight, graph_vocabulary, graph_list_k
        # D4 (27/11/2026): when a document repeats among the first ``hop_k`` passages and the question names a pest or an
        # ingredient, the closest fragment (dense) that names one of them in a document not yet there takes the place
        # of the last repeated passage. Needs the mentions table (interfaces.jobs.vocabulary menciones).
        self.entity_hop, self.hop_k = entity_hop, hop_k
        self.ultimo_salto: dict | None = None

    def lexical_query(self, question: str) -> str:
        if self.vocabulary is None:
            return question
        return " ".join([question, *self.vocabulary.expand(question)])

    def _lex(self) -> str:
        if self.lexical_header == "sin":
            return "to_tsvector('spanish', f.texto)"
        if self.lexical_header == "peso":
            return "(setweight(to_tsvector('spanish', f.encabezado), 'D') || setweight(to_tsvector('spanish', f.texto), 'A'))"
        return "f.lexico"

    def _idf(self, lexemes: list[str]) -> dict[str, float]:
        """BM25 idf per stemmed lexeme over the non-parent fragments of this signature (cached per retriever)."""
        import math

        cache = self.__dict__.setdefault(f"_df_{self.lexical_header}", {})
        if "__N__" not in cache:
            cache["__N__"] = self.conn.execute("SELECT count(*) FROM fragmentos WHERE firma = %s AND rol <> 'parent'",
                                               (self.signature,)).fetchone()[0]
        for lx in lexemes:
            if lx not in cache:
                cache[lx] = self.conn.execute(
                    f"SELECT count(*) FROM fragmentos f WHERE f.firma = %s AND f.rol <> 'parent' AND {self._lex()} @@ plainto_tsquery('simple', %s)",
                    (self.signature, lx)).fetchone()[0]
        n = cache["__N__"]
        return {lx: math.log((n - cache[lx] + 0.5) / (cache[lx] + 0.5) + 1) for lx in lexemes}

    def lexical(self, question: str) -> list[str]:
        question = self.lexical_query(question)
        if self.lexical_ranking == "idf":
            # a rare term («erysiphe», 452 of 21 807 fragments) must outweigh common ones («desarrolla», 6 015):
            # ts_rank_cd has no idf, so with a large corpus the common words decide the order
            lexemes = [r[0] for r in self.conn.execute(
                "SELECT DISTINCT unnest(tsvector_to_array(to_tsvector('spanish', %s)))", (question,)).fetchall()]
            if not lexemes:
                return []
            idf = self._idf(lexemes)
            lex = self._lex()
            score = " + ".join([f"%s * ts_rank_cd({lex}, plainto_tsquery('simple', %s), 1)"] * len(lexemes))
            params = [v for lx in lexemes for v in (idf[lx], lx)]
            rows = self.conn.execute(
                f"""WITH q AS (SELECT NULLIF(replace(plainto_tsquery('spanish', %s)::text, '&', '|'), '')::tsquery AS q)
                    SELECT f.chunk_id FROM fragmentos f, q
                    WHERE q.q IS NOT NULL AND f.firma = %s AND f.rol <> 'parent' AND {lex} @@ q.q
                    ORDER BY ({score}) DESC LIMIT %s""",
                (question, self.signature, *params, self.k_lexical)).fetchall()
            return [r[0] for r in rows]
        lex = self._lex()
        rows = self.conn.execute(
            f"""WITH q AS (SELECT NULLIF(replace(plainto_tsquery('spanish', %s)::text, '&', '|'), '')::tsquery AS q)
               SELECT f.chunk_id FROM fragmentos f, q
               WHERE q.q IS NOT NULL AND f.firma = %s AND f.rol <> 'parent' AND {lex} @@ q.q
               ORDER BY ts_rank_cd({lex}, q.q) DESC LIMIT %s""",
            (question, self.signature, self.k_lexical)).fetchall()
        return [r[0] for r in rows]

    def graph_list(self, question: str) -> list[str]:
        """Fragments that name the graph terms of the question (pests, ingredients, crops) by any of their names, scored
        by how many distinct terms they name (a crop counts half), the best fragment of each document, first
        ``graph_list_k``. A question that only names crops has no list (every fragment of a crop would tie)."""
        from knowledge.vocabulary.agrovoc import norm

        if self.graph_vocabulary is None:
            return []
        terms = self.graph_vocabulary.find(question)
        if not any(t.kind != "crop" for t in terms):
            return []
        conds, params = [], []
        for t in terms:
            labels = sorted({lab.strip() for lab in t.labels if len(norm(lab)) >= 4 or t.kind == "crop"})
            if labels:
                conds.append((0.5 if t.kind == "crop" else 1.0,
                              " || ".join(["phraseto_tsquery('spanish', %s)"] * len(labels))))
                params.append(labels)
        if not conds:
            return []
        lex = self._lex()
        score = " + ".join(f"(CASE WHEN {lex} @@ ({q}) THEN {w} ELSE 0 END)" for w, q in conds)
        anyq = " || ".join(f"({q})" for _, q in conds)
        flat = [x for labels in params for x in labels]
        rows = self.conn.execute(
            f"""SELECT f.chunk_id, f.doc_id, ({score}) AS s FROM fragmentos f
                WHERE f.firma = %s AND f.rol <> 'parent' AND {lex} @@ ({anyq})
                ORDER BY s DESC, ts_rank_cd({lex}, ({anyq})) DESC, f.chunk_id LIMIT 400""",
            (*flat, self.signature, *flat, *flat)).fetchall()
        out, docs = [], set()
        for cid, doc, _ in rows:
            if doc not in docs:
                docs.add(doc)
                out.append(cid)
            if len(out) == self.graph_list_k:
                break
        return out

    def dense(self, question: str) -> list[tuple[str, float]]:
        vec = vector_literal(self.embedder.encode([question])[0])
        self._vector = (question, vec)
        rows = self.conn.execute(
            """SELECT v.chunk_id, 1 - (v.vector <=> %s::vector) AS sim
               FROM vectores v JOIN fragmentos f ON f.chunk_id = v.chunk_id AND f.firma = v.firma
               WHERE v.firma = %s AND v.modelo = %s AND f.rol <> 'parent'
               ORDER BY v.vector <=> %s::vector LIMIT %s""",
            (vec, self.signature, self.embedder.name, vec, self.k_dense)).fetchall()
        return [(r[0], float(r[1])) for r in rows]

    def retrieve(self, question: str) -> list[Passage]:
        lex = self.lexical(question)
        den = self.dense(question)
        scores: dict[str, float] = {}
        for rank, cid in enumerate(lex, start=1):
            scores[cid] = scores.get(cid, 0.0) + self.lexical_weight / (self.rrf_k + rank)
        for rank, (cid, _) in enumerate(den, start=1):
            scores[cid] = scores.get(cid, 0.0) + self.dense_weight / (self.rrf_k + rank)
        graph = self.graph_list(question) if self.graph_list_weight else []
        for rank, cid in enumerate(graph, start=1):
            scores[cid] = scores.get(cid, 0.0) + self.graph_list_weight / (self.rrf_k + rank)
        if self.generic_weight != 1.0 and scores:
            for cid, section in self.conn.execute("SELECT chunk_id, seccion FROM fragmentos WHERE firma = %s AND chunk_id = ANY(%s)",
                                                   (self.signature, list(scores))).fetchall():
                if is_generic(tuple(section or ())):
                    scores[cid] *= self.generic_weight
        lex_rank = {cid: i for i, cid in enumerate(lex, start=1)}
        graph_rank = {cid: i for i, cid in enumerate(graph, start=1)}
        den_rank = {cid: (i, s) for i, (cid, s) in enumerate(den, start=1)}
        # evidence: a lexical match (a fragment of the graph list names a term of the question), or a dense
        # similarity above the floor
        eligible = [cid for cid in scores if cid in lex_rank or cid in graph_rank
                    or den_rank.get(cid, (0, 0.0))[1] >= self.min_dense_score]
        ranked = sorted(eligible, key=lambda c: scores[c], reverse=True)
        if self.max_per_document and ranked:
            ranked = self._cap_per_document(ranked)
        best = self._mmr(ranked, scores) if self.mmr_lambda is not None else ranked[: self.top_k]
        self.ultimo_salto = None
        if self.entity_hop and best:
            best = self._segundo_salto(question, best, scores)
        if not best:
            return []
        rows = self.conn.execute(
            """SELECT f.chunk_id, f.doc_id, d.titulo, d.fuente, d.nivel, d.url, f.seccion, f.paginas, f.texto,
                      f.encabezado, f.padre, p.texto
               FROM fragmentos f JOIN documentos d ON d.doc_id = f.doc_id
               LEFT JOIN fragmentos p ON p.chunk_id = f.padre AND p.firma = f.firma
               WHERE f.firma = %s AND f.chunk_id = ANY(%s)""", (self.signature, best)).fetchall()
        by_id = {r[0]: r for r in rows}
        out = []
        for cid in best:
            r = by_id[cid]
            out.append(Passage(chunk_id=cid, doc_id=r[1], title=r[2], source=r[3], level=r[4], url=r[5],
                               section=list(r[6] or []), pages=list(r[7] or []), text=r[8], header=r[9],
                               score=round(scores[cid], 5), lexical_rank=lex_rank.get(cid),
                               dense_rank=den_rank.get(cid, (None, None))[0],
                               dense_score=round(den_rank[cid][1], 4) if cid in den_rank else None, context=r[11] or ""))
        if self.neighbors:
            self._add_neighbors(out)
        return out

    def _segundo_salto(self, question: str, best: list[str], scores: dict[str, float]) -> list[str]:
        terms = [t for t in (self.graph_vocabulary.find(question) if self.graph_vocabulary else []) if t.kind != "crop"]
        if not terms:
            return best
        head = best[: self.hop_k]
        docs = dict(self.conn.execute("SELECT chunk_id, doc_id FROM fragmentos WHERE firma = %s AND chunk_id = ANY(%s)",
                                      (self.signature, head)).fetchall())
        vistos, repetido = [], None
        for i, c in enumerate(head):
            if docs.get(c) in vistos:
                repetido = i
            else:
                vistos.append(docs.get(c))
        if repetido is None:
            return best
        if getattr(self, "_vector", (None,))[0] != question:
            self.dense(question)
        vec = self._vector[1]
        row = self.conn.execute(
            """SELECT m.chunk_id, m.doc_id, 1 - (v.vector <=> %s::vector) AS sim
               FROM (SELECT DISTINCT chunk_id, doc_id FROM menciones
                     WHERE firma = %s AND tipo || ':' || clave = ANY(%s) AND doc_id <> ALL(%s)) m
               JOIN vectores v ON v.chunk_id = m.chunk_id AND v.firma = %s AND v.modelo = %s
               ORDER BY v.vector <=> %s::vector LIMIT 1""",
            (vec, self.signature, [f"{t.kind}:{t.key}" for t in terms], vistos, self.signature, self.embedder.name,
             vec)).fetchone()
        if not row or row[2] < self.min_dense_score:
            return best
        nuevo, quitado = row[0], best[repetido]
        salida = [c for c in best if c != nuevo]
        salida[repetido] = nuevo
        if len(best) > self.hop_k:                          # the displaced passage stays right after the first ones
            salida.insert(self.hop_k, quitado)
        scores[nuevo] = scores.get(quitado, 0.0)
        self.ultimo_salto = {"terminos": [f"{t.kind}:{t.key}" for t in terms], "nuevo": nuevo, "documento": row[1],
                             "similitud": round(float(row[2]), 4), "reemplaza": quitado, "posicion": repetido + 1}
        return salida[: len(best)]

    def _cap_per_document(self, ranked: list[str]) -> list[str]:
        """Keeps the order and drops the fragments of a document beyond the first ``max_per_document``."""
        docs = dict(self.conn.execute("SELECT chunk_id, doc_id FROM fragmentos WHERE firma = %s AND chunk_id = ANY(%s)",
                                      (self.signature, ranked)).fetchall())
        vistos: dict[str, int] = {}
        out = []
        for c in ranked:
            d = docs.get(c, c)
            if vistos.get(d, 0) < self.max_per_document:
                out.append(c)
                vistos[d] = vistos.get(d, 0) + 1
        return out

    def _mmr(self, ranked: list[str], scores: dict[str, float]) -> list[str]:
        """Maximal marginal relevance over the fused candidates, with the stored fragment vectors (cosine)."""
        import numpy as np

        pool = ranked[: max(self.top_k * 3, 30)]
        rows = self.conn.execute("SELECT chunk_id, vector::text FROM vectores WHERE firma = %s AND modelo = %s AND chunk_id = ANY(%s)",
                                 (self.signature, self.embedder.name, pool)).fetchall()
        vec = {cid: np.array(json.loads(v), dtype=np.float32) for cid, v in rows}
        top = max(scores[c] for c in pool)
        chosen: list[str] = []
        rest = list(pool)
        while rest and len(chosen) < self.top_k:
            def gain(c: str) -> float:
                sim = max((float(vec[c] @ vec[s]) for s in chosen if c in vec and s in vec), default=0.0)
                return self.mmr_lambda * scores[c] / top - (1 - self.mmr_lambda) * sim
            best = max(rest, key=gain)
            chosen.append(best)
            rest.remove(best)
        return chosen

    def _add_neighbors(self, passages: list[Passage]) -> None:
        """The previous and next ``neighbors`` fragments of the same document and section, in order, as the context the
        generator reads (only where the hit has no parent of its own)."""
        for p in passages:
            if p.context:
                continue
            rows = self.conn.execute(
                """WITH h AS (SELECT doc_id, orden, seccion FROM fragmentos WHERE firma = %s AND chunk_id = %s)
                   SELECT f.texto FROM fragmentos f, h
                   WHERE f.firma = %s AND f.doc_id = h.doc_id AND f.seccion = h.seccion AND f.rol <> 'parent'
                     AND f.orden BETWEEN h.orden - %s AND h.orden + %s
                   ORDER BY f.orden""", (self.signature, p.chunk_id, self.signature, self.neighbors, self.neighbors)).fetchall()
            if len(rows) > 1:
                p.context = "\n\n".join(r[0] for r in rows)
