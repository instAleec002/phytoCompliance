"""Stage 3 retrieval options without a database: V3b (header in the lexical index), MMR and neighbors."""
import json

import pytest

from assistant.retrieval.search import HybridRetriever, Passage


class FakeConn:
    """Returns canned rows by a substring of the SQL; records every query."""

    def __init__(self, answers: dict[str, list[tuple]]):
        self.answers, self.queries = answers, []

    def execute(self, sql, params=()):
        self.queries.append((sql, params))
        rows = next((r for key, r in self.answers.items() if key in sql), [])
        return type("R", (), {"fetchall": lambda _self: rows, "fetchone": lambda _self: rows[0] if rows else None})()


class Emb:
    name = "bge-m3"


def retriever(conn, **opts):
    return HybridRetriever(conn, Emb(), "firma1", top_k=2, **opts)


def test_v3b_lexical_expression():
    assert retriever(FakeConn({}))._lex() == "f.lexico"
    assert retriever(FakeConn({}), lexical_header="sin")._lex() == "to_tsvector('spanish', f.texto)"
    peso = retriever(FakeConn({}), lexical_header="peso")._lex()
    assert "'D'" in peso and "'A'" in peso and "encabezado" in peso
    with pytest.raises(ValueError):
        retriever(FakeConn({}), lexical_header="otro")


def test_mmr_skips_a_near_copy():
    # a and b are almost the same vector (a thesis repeating a paragraph); c is different but a bit less relevant
    vecs = {"a": [1.0, 0.0], "b": [0.999, 0.045], "c": [0.0, 1.0]}
    conn = FakeConn({"FROM vectores": [(k, json.dumps(v)) for k, v in vecs.items()]})
    scores = {"a": 1.0, "b": 0.95, "c": 0.8}
    assert retriever(conn, mmr_lambda=0.5)._mmr(["a", "b", "c"], scores) == ["a", "c"]
    assert retriever(conn, mmr_lambda=1.0)._mmr(["a", "b", "c"], scores) == ["a", "b"]    # λ = 1: plain relevance


def test_neighbors_fill_context_only_where_there_is_no_parent():
    conn = FakeConn({"BETWEEN h.orden": [("anterior",), ("el acierto",), ("siguiente",)]})
    hit = Passage("d:0002:x", "d", "Manual", "senasa", "A", "", ["3. Oídio"], [4], "el acierto", "", 1.0)
    child = Passage("d:0005:y", "d", "Manual", "senasa", "A", "", ["3. Oídio"], [5], "hijo", "", 0.9, context="padre")
    retriever(conn, neighbors=1)._add_neighbors([hit, child])
    assert hit.context == "anterior\n\nel acierto\n\nsiguiente" and hit.text == "el acierto"   # the citation keeps the hit
    assert child.context == "padre"                                                            # a parent wins
    assert len(conn.queries) == 1
