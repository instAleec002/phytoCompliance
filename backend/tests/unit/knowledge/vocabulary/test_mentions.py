"""D4: the graph terms a whole fragment names, read left to right with the longest label at each word."""
from knowledge.vocabulary.index import Vocabulary


def _v():
    return Vocabulary.build(None, [("000437", "Erysiphe necator", "Oidiosis"), ("000626", "Botrytis cinerea", "Moho gris")],
                            {"sulphur": "azufre"})


def test_mentions_finds_each_term_once_by_any_of_its_names():
    texto = "El oídio (Erysiphe necator) de la vid se controla con azufre; la Botrytis cinerea no responde al azufre."
    assert _v().mentions(texto) == {("pest", "000437"), ("crop", "table_grape"), ("ingredient", "sulphur"),
                                    ("pest", "000626")}


def test_mentions_agrees_with_find_on_a_question():
    v = _v()
    q = "¿Cómo se controla la oidiosis en uva de mesa?"
    assert v.mentions(q) == {(t.kind, t.key) for t in v.find(q)}
    assert v.mentions("") == set()
