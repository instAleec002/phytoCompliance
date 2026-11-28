"""Multi-hop questions (stage 5): the question split into sub-questions, each one searched, and the lists fused.

A single search with the whole question seldom brings back the two passages a multi-hop question needs (S2: about
half of them had no answering chunk in the first ten). ``Descomponedor`` asks the local model for at most three
self-contained sub-questions with Ollama's structured output (the JSON Schema of ``Subpreguntas``), so the answer is
valid JSON or the question is kept as it is. ``RecuperadorMultipregunta`` searches the whole question and each
sub-question with the same retriever and fuses the lists with reciprocal rank fusion; for anything else it behaves as
the retriever it wraps."""
from __future__ import annotations

import json
import unicodedata

import httpx
from pydantic import BaseModel, Field, ValidationError

INSTRUCCION = """Divide la pregunta del usuario en subpreguntas de búsqueda.
Si pide información sobre dos o más cosas distintas (por ejemplo dos plagas o dos cultivos, una causa y su control, un
síntoma y su manejo, o datos que estarían en documentos distintos), escribe una subpregunta por cada cosa, como máximo
tres, cada una completa y entendible por sí sola (repite el cultivo o la plaga si hace falta).
Si pide una sola cosa, devuelve la misma pregunta como única subpregunta.
Responde solo con el JSON pedido."""


class Subpreguntas(BaseModel):
    subpreguntas: list[str] = Field(min_length=1, max_length=3)


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return " ".join("".join(ch if ch.isalnum() else " " for ch in t).split())


class Descomponedor:
    def __init__(self, base_url: str, model: str, timeout_s: float = 120):
        self.url = base_url.rstrip("/").removesuffix("/v1") + "/api/chat"
        self.model = model
        self.http = httpx.Client(timeout=timeout_s)

    def __call__(self, pregunta: str) -> list[str]:
        try:
            r = self.http.post(self.url, json={
                "model": self.model, "stream": False, "think": False, "format": Subpreguntas.model_json_schema(),
                "options": {"temperature": 0, "seed": 20261127},
                "messages": [{"role": "system", "content": INSTRUCCION}, {"role": "user", "content": pregunta}]})
            r.raise_for_status()
            subs = Subpreguntas.model_validate(json.loads(r.json()["message"]["content"])).subpreguntas
        except (httpx.HTTPError, KeyError, json.JSONDecodeError, ValidationError):
            return [pregunta]                                    # ante cualquier falla, la pregunta tal cual
        limpias = [s.strip() for s in subs if s and len(s.strip()) > 5]
        return limpias[:3] or [pregunta]


class RecuperadorMultipregunta:
    """Wraps a retriever: ``retrieve`` searches the question and its sub-questions and fuses the lists (RRF)."""

    def __init__(self, base, descomponer, rrf_k: int = 60):
        self.base, self.descomponer, self.rrf_k = base, descomponer, rrf_k
        self.ultimas: list[str] = []                             # las subpreguntas de la última búsqueda (traza)

    def __getattr__(self, nombre):                               # signature, embedder, lexical, dense, top_k…
        return getattr(self.base, nombre)

    def retrieve(self, question: str):
        subs = self.descomponer(question)
        consultas = [question] + [s for s in subs if _norm(s) != _norm(question)]
        self.ultimas = consultas[1:]
        if len(consultas) == 1:
            return self.base.retrieve(question)
        puntaje, pasaje = {}, {}
        for consulta in consultas:
            for rango, p in enumerate(self.base.retrieve(consulta), start=1):
                puntaje[p.chunk_id] = puntaje.get(p.chunk_id, 0.0) + 1.0 / (self.rrf_k + rango)
                pasaje.setdefault(p.chunk_id, p)
        orden = sorted(puntaje, key=lambda c: puntaje[c], reverse=True)
        return [pasaje[c] for c in orden[: self.base.top_k]]
