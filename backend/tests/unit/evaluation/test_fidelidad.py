"""Sentence-level faithfulness: the split every judge and the annotator share, the label parser, and the measures."""
from evaluation.fidelidad import _parse, cohen_kappa, fidelidad, juzgar, oraciones


def test_sentences_keep_citation_marks_and_drop_markdown():
    texto = ("La plaga que representa un riesgo es la **mosca de la fruta (Ceratitis capitata)**. [2]\n"
             "- Se aplica 0.5 L/ha de azufre en floración [1]. El transporte no debe demorar más de 48 horas [2].")
    assert oraciones(texto) == [
        "La plaga que representa un riesgo es la mosca de la fruta (Ceratitis capitata). [2]",
        "Se aplica 0.5 L/ha de azufre en floración [1].",
        "El transporte no debe demorar más de 48 horas [2].",
    ]


def test_decimals_and_short_headings_do_not_make_sentences():
    assert oraciones("Dosis:\nUsar 2.5 kg/ha en 200 L de agua por cilindro [1].") == [
        "Dosis: Usar 2.5 kg/ha en 200 L de agua por cilindro [1]."]
    assert oraciones("") == []


def test_parse_maps_labels_by_index_and_ignores_unknown_ones():
    out = _parse('{"veredictos": [{"i": 2, "v": "Ausente"}, {"i": 1, "v": "respaldada"}, {"i": 9, "v": "mezcla"},'
                 ' {"i": 3, "v": "quizás"}]}', 3)
    assert out == ["respaldada", "ausente", None]
    assert _parse("sin json", 2) == [None, None]


def test_faithfulness_counts_unlabelled_as_not_supported():
    assert fidelidad(["respaldada", "ausente", None, "respaldada"]) == 0.5
    assert fidelidad([]) is None


def test_kappa():
    assert cohen_kappa([1, 1, 0, 0], [1, 1, 0, 0]) == 1.0
    assert cohen_kappa([1, 0, 1, 0], [0, 1, 0, 1]) == -1.0
    assert cohen_kappa([], []) is None


class _Juez:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)

    def chat(self, system, prompt):
        return self.respuestas.pop(0)


def test_judge_retries_only_until_every_sentence_has_a_label():
    j = _Juez(['{"veredictos": [{"i": 1, "v": "respaldada"}]}', '{"veredictos": [{"i": 2, "v": "mezcla"}]}'])
    assert juzgar(j, ["a b c d", "e f g h"], ["[1] pasaje"]) == ["respaldada", "mezcla"]
    assert j.respuestas == []
