"""D3: the graph list of the fusion is off without a vocabulary and empty when the question only names crops."""
from assistant.retrieval.search import HybridRetriever
from knowledge.vocabulary.index import Term


class _Vocabulario:
    def __init__(self, terms):
        self.terms = terms

    def find(self, text):
        return self.terms


class _SinConsultas:
    def execute(self, *a, **k):
        raise AssertionError("no debe consultar la base")


def _r(vocabulario):
    return HybridRetriever(_SinConsultas(), None, "firma", graph_list_weight=1.0, graph_vocabulary=vocabulario)


def test_no_vocabulary_or_only_crops_gives_no_list():
    assert _r(None).graph_list("¿Qué plagas tiene el palto?") == []
    solo_cultivo = _Vocabulario([Term("crop", "avocado", {"palto", "palta"})])
    assert _r(solo_cultivo).graph_list("¿Qué plagas tiene el palto?") == []
