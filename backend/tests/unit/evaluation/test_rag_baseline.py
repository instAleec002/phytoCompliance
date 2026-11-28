from dataclasses import dataclass

from evaluation.rag_baseline import RagConvencional, citados


@dataclass
class _P:
    title: str
    section: list
    text: str


class _Ret:
    def retrieve(self, q):
        return [_P("Guía", ["Plagas"], "uno"), _P("Tesis", ["Control"], "dos")]


class _Gen:
    def __init__(self):
        self.prompts = []

    def generate(self, system, prompt):
        self.prompts.append(prompt)
        return type("G", (), {"text": "Se usa X [2] y también [1, 2] y [7]."})()


def test_only_existing_passages_count_as_cited():
    assert citados("a [2] b [1, 2] c [7]", 2) == [2, 1]


def test_baseline_answers_from_numbered_passages_without_tools():
    g = _Gen()
    r = RagConvencional(_Ret(), g).responder("¿Cómo se controla?")
    assert r.citados == [2, 1] and len(r.pasajes) == 2
    assert "[1] Guía (Plagas): uno" in g.prompts[0] and "Pregunta: ¿Cómo se controla?" in g.prompts[0]
