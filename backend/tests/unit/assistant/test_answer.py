"""The answerer with a fake retriever and a fake generator: follow-up questions are rewritten with the history before
retrieval, only the citations the text uses are kept, and missing evidence gives the fixed abstention."""
from assistant.answer import Answerer
from assistant.generation.prompt import CONDENSE, NO_EVIDENCE, build_prompt, history_text
from assistant.retrieval.search import Passage


def passage(n: int, text: str) -> Passage:
    return Passage(chunk_id=f"c{n}", doc_id=f"d{n}", title=f"Manual {n}", source="inia", level="A", url=f"u{n}",
                   section=["IV. Manejo"], pages=[n], text=text, header="", score=0.1)


class FakeRetriever:
    signature = "sig"

    class embedder:
        name = "fake"

    def __init__(self, passages):
        self.passages, self.queries = passages, []

    def retrieve(self, q):
        self.queries.append(q)
        return list(self.passages)


class FakeGenerator:
    name = "fake"

    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def generate(self, system, prompt):
        self.calls.append((system, prompt))
        text = "control de Botrytis en palto" if system == CONDENSE else self.answer
        return type("G", (), {"text": text, "seconds": 0.1, "model": "fake", "usage": {}})()


def test_answer_keeps_only_used_citations():
    ps = [passage(1, "Botrytis se controla con podas."), passage(2, "Otro tema."), passage(3, "Rotar fungicidas.")]
    a = Answerer(FakeRetriever(ps), FakeGenerator("Podar [1] y rotar [3]. [9] no existe."), top_k=3)
    r = a.answer("¿Cómo controlo Botrytis?")
    assert r.evidence and [c.n for c in r.citations] == [1, 3] and r.citations[1].chunk_id == "c3"
    assert r.trace["standalone_query"] == "¿Cómo controlo Botrytis?"          # no history: no rewrite


def test_follow_up_is_rewritten_with_history_and_history_reaches_the_prompt():
    retriever = FakeRetriever([passage(1, "En palto, Botrytis se maneja con ventilación.")])
    gen = FakeGenerator("Ventilar [1].")
    a = Answerer(retriever, gen, top_k=3)
    history = [("usuario", "¿Cómo se maneja Botrytis en arándano?"), ("asistente", "Con podas [1].")]
    r = a.answer("¿y en palto?", history)
    assert retriever.queries == ["control de Botrytis en palto"]
    assert r.trace["standalone_query"] == "control de Botrytis en palto" and r.trace["history_messages"] == 2
    _system, prompt = gen.calls[-1]
    assert "Conversación previa:" in prompt and "Usuario: ¿Cómo se maneja Botrytis en arándano?" in prompt
    assert prompt.endswith("Pregunta: ¿y en palto?")


def test_abstains_without_passages_or_when_the_generator_finds_no_support():
    assert Answerer(FakeRetriever([]), FakeGenerator("x"), 3).answer("¿Mango?").text == NO_EVIDENCE
    r = Answerer(FakeRetriever([passage(1, "Otro tema.")]), FakeGenerator(NO_EVIDENCE), 3).answer("¿Mango?")
    assert not r.evidence and r.citations == []


def test_history_is_trimmed_from_the_oldest_and_prompt_numbers_passages():
    hist = [("usuario", "a" * 50), ("asistente", "b" * 50), ("usuario", "c" * 50)]
    text = history_text(hist, max_chars=130)
    assert "a" * 50 not in text and text.endswith("c" * 50)
    prompt = build_prompt("¿Q?", [passage(1, "uno"), passage(2, "dos")])
    assert "[1] Manual 1 (IV. Manejo, p. 1)\nuno" in prompt and "[2] Manual 2" in prompt
