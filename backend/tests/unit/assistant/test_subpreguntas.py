from dataclasses import dataclass

from assistant.orchestration.subpreguntas import RecuperadorMultipregunta


@dataclass
class _P:
    chunk_id: str


class _Base:
    top_k = 3
    signature = "firma"

    def __init__(self, listas):
        self.listas, self.vistas = listas, []

    def retrieve(self, q):
        self.vistas.append(q)
        return [_P(c) for c in self.listas[q]]


def test_simple_question_is_one_search():
    base = _Base({"q": ["a", "b"]})
    r = RecuperadorMultipregunta(base, lambda q: [q])
    assert [p.chunk_id for p in r.retrieve("q")] == ["a", "b"] and base.vistas == ["q"] and r.ultimas == []


def test_sub_questions_are_fused_with_rrf_and_the_rest_delegates():
    base = _Base({"q": ["a", "x"], "sub1": ["a", "b"], "sub2": ["c", "a"]})
    r = RecuperadorMultipregunta(base, lambda q: ["sub1", "sub2"])
    ids = [p.chunk_id for p in r.retrieve("q")]
    assert ids[0] == "a"                                   # aparece en las tres listas
    assert len(ids) == 3 and set(ids) <= {"a", "b", "c", "x"}
    assert r.ultimas == ["sub1", "sub2"] and r.signature == "firma"
