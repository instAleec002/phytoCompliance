"""Faithfulness at the sentence level, so that several judges and a human annotator grade the same units.

RAGAS defines faithfulness as the share of an answer's statements supported by its context. The first runs let the
judge split the answer itself, so two judges (or a judge and a person) never graded the same statements. Here the
statements are the answer's sentences, split without a language model, and each judge labels every sentence against
the passages and exact-core rows the answer cites:

- ``respaldada``: what the sentence states is in the cited evidence (paraphrase allowed);
- ``mezcla``: it joins facts of different passages into something none of them says;
- ``ausente``: it states something no cited passage says;
- ``contradice``: a cited passage says the opposite.

Faithfulness is the share of ``respaldada`` sentences. The labels also type the errors, which is what the error
analysis of multi-hop questions needs (review of the short paper, 26/11/2026).

The split, the prompt and the local judge live in ``assistant.orchestration.verificacion`` since 27/11/2026, because
the assistant uses the same check on its own answers; they are re-exported here for the evaluation."""
from __future__ import annotations

from assistant.orchestration.verificacion import (  # noqa: F401  (re-exported for the evaluation)
    JUEZ_ORACIONES,
    VEREDICTOS,
    Juez,
    _parse,
    juzgar,
    oraciones,
    reintentar,
)


def fidelidad(veredictos: list[str | None]) -> float | None:
    """Share of supported sentences; a sentence without a label counts as not supported."""
    return round(sum(v == "respaldada" for v in veredictos) / len(veredictos), 3) if veredictos else None


def cohen_kappa(a: list, b: list) -> float | None:
    if not a or len(a) != len(b):
        return None
    cats = sorted(set(a) | set(b))
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    return round((po - pe) / (1 - pe), 3) if pe < 1 else 1.0
