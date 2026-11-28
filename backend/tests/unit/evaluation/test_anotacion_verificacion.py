"""The human check of the sentence-level verification: what an answer said before the check and what it kept."""
from interfaces.jobs.evaluate import _antes_despues, _textos


def _ev(*refs):
    return [{"ref": r, "doc_id": "d", "texto": f"pasaje  {r}\n"} for r in refs]


def test_checked_answer_gives_the_original_sentences_and_the_kept_ones():
    x = {"texto_sin_verificar": "Se aplica azufre en floración [1]. El transporte dura 48 horas [2].",
         "evidencia_sin_verificar": _ev("[1]", "[2]"), "oraciones": ["Se aplica azufre en floración [1]."]}
    antes, ev, despues = _antes_despues(x)
    assert antes == ["Se aplica azufre en floración [1].", "El transporte dura 48 horas [2]."]
    assert [e["ref"] for e in ev] == ["[1]", "[2]"]
    assert despues == ["Se aplica azufre en floración [1]."]


def test_unchanged_answer_is_the_same_before_and_after_and_an_abstention_has_no_sentences():
    x = {"texto_sin_verificar": None, "evidencia_citada": _ev("[1]"), "oraciones": ["Una oración [1]."]}
    assert _antes_despues(x) == (["Una oración [1]."], _ev("[1]"), ["Una oración [1]."])
    vacia = {"texto_sin_verificar": "Algo sin citas.", "evidencia_sin_verificar": [], "oraciones": []}
    assert _antes_despues(vacia) == ([], [], [])


def test_passage_texts_compare_without_whitespace_differences():
    assert _textos(_ev("[1]")) == {"[1]": "pasaje [1]"}
