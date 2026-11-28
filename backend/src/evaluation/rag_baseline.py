"""Conventional RAG baseline for the short paper (rule fixed in pendientes/26 on 24/11/2026).

The same hybrid retrieval as the system (chunking V7, six passages) and the same local model (Qwen3-8B, reasoning off,
temperature zero), but no tools, no graph and no guard: the model answers only from the retrieved passages and cites
them by number. This is the pipeline the architecture is compared against.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

SISTEMA = ("Eres un asistente técnico agrícola. Responde la pregunta usando solo los pasajes numerados. Cita cada dato "
           "con el número del pasaje entre corchetes, por ejemplo [1]. Si los pasajes no contienen la respuesta, dilo.")


@dataclass
class RespuestaRag:
    texto: str
    pasajes: list = field(default_factory=list)          # the retrieved passages, in order (1-based for citations)
    citados: list[int] = field(default_factory=list)     # passage numbers the answer cites and that exist
    segundos: float = 0.0


def citados(texto: str, n: int) -> list[int]:
    """Numbers in [k] or [k, j] that point to an existing passage, in order of first appearance."""
    vistos = []
    for grupo in re.findall(r"\[([\d,\s]+)\]", texto):
        for k in re.findall(r"\d+", grupo):
            k = int(k)
            if 1 <= k <= n and k not in vistos:
                vistos.append(k)
    return vistos


class RagConvencional:
    def __init__(self, retriever, generador, caracteres_por_pasaje: int = 1200):
        self.retriever, self.gen, self.max_chars = retriever, generador, caracteres_por_pasaje

    def responder(self, pregunta: str) -> RespuestaRag:
        t0 = time.perf_counter()
        pasajes = self.retriever.retrieve(pregunta)
        bloque = "\n\n".join(f"[{i}] {p.title} ({', '.join(p.section)}): {p.text[: self.max_chars]}"
                             for i, p in enumerate(pasajes, 1))
        texto = self.gen.generate(SISTEMA, f"Pasajes:\n{bloque}\n\nPregunta: {pregunta}").text.strip()
        return RespuestaRag(texto, pasajes, citados(texto, len(pasajes)), round(time.perf_counter() - t0, 2))
