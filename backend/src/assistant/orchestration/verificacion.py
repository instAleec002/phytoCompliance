"""Checks the assistant runs on its own answer before showing it (improvements of 27/11/2026).

Two checks, both measured against what the answer itself cites:

- values (output guard): a limit in mg/kg or an interval in days that no tool returned. The evaluation counted these
  as invented values; measured with Gemma 4 E4B, the model received 1.0 mg/kg from ``limite_maximo`` and wrote today's
  0.01 from memory. The agent now sends such an answer back to the model once before accepting it.
- sentences: each sentence of the final answer is labelled by a verifier model against the passages and graph rows
  the answer cites (supported, mixed, absent, contradicted), and only supported sentences are kept. The verifier should
  be a model of another family than the generator, and never the judge that later grades the answers.

The sentence split and the labelling prompt are the ones of the faithfulness evaluation (evaluation/fidelidad.py),
so what the assistant checks and what the evaluation measures are the same units."""
from __future__ import annotations

import json
import re
import time

import httpx

VEREDICTOS = ("respaldada", "mezcla", "ausente", "contradice")

JUEZ_ORACIONES = """Eres un juez de fidelidad. Recibes las oraciones numeradas de una respuesta y la evidencia que la
respuesta cita (pasajes de documentos y, a veces, filas de una base de datos marcadas [G1], [G2]...). Para cada
oración decide, usando solo esa evidencia y nunca tu propio conocimiento:
respaldada = lo que afirma está en la evidencia (puede estar dicho con otras palabras);
mezcla = junta datos de pasajes distintos en algo que ninguno dice (por ejemplo, la dosis de un producto con el
cultivo o la plaga de otro);
ausente = afirma algo que no está en ningún pasaje ni fila;
contradice = la evidencia dice lo contrario.
Una oración que solo dice que no hay información suficiente es respaldada si la evidencia no trae ese dato.
Responde solo JSON: {"veredictos": [{"i": 1, "v": "respaldada"}, {"i": 2, "v": "ausente"}]} con una entrada por
oración, en el mismo orden."""

_CORTE = re.compile(r"(?<=[.!?…])\s+(?=[\[¿¡(«\"*A-ZÁÉÍÓÚÑ0-9-])|\n+")
_MARCAS = re.compile(r"\*\*|__|(?<!\w)[*_](?!\s)|(?<!\S)[*_](?=\w)")
_VIÑETA = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
NUM = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)(?![\w])")
CON_UNIDAD = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:mg/kg|d[ií]as?)")


def oraciones(texto: str, minimo: int = 4) -> list[str]:
    """The answer's sentences: split at sentence ends and line breaks, markdown emphasis and list markers removed.

    A piece shorter than ``minimo`` words (a lone «[2].» after a sentence, a heading) joins the previous one, so
    citation marks stay with the sentence they support; a short piece at the start (a heading) joins the next one."""
    piezas, pendiente = [], ""
    for linea in _CORTE.split(texto.strip()):
        s = _VIÑETA.sub("", _MARCAS.sub("", linea)).strip()
        if not s:
            continue
        corta = len(re.findall(r"[\wáéíóúñ]+", s)) < minimo
        if corta and piezas:
            piezas[-1] = f"{piezas[-1]} {s}"
        elif corta:
            pendiente = f"{pendiente} {s}".strip()
        else:
            piezas.append(f"{pendiente} {s}".strip())
            pendiente = ""
    if pendiente:
        piezas.append(pendiente)
    return piezas


def numeros(text: str) -> list[float]:
    return [float(x.replace(",", ".")) for x in NUM.findall(text or "")]


def valores_sin_respaldo(texto: str, llamadas: list[dict]) -> list[float]:
    """Values given with a unit (mg/kg or días) that no tool result contains."""
    devueltos = numeros(json.dumps([c.get("resultado") for c in llamadas], ensure_ascii=False))
    con_unidad = [float(m.group(1).replace(",", ".")) for m in CON_UNIDAD.finditer(texto or "")]
    return [v for v in con_unidad if not any(abs(v - d) < 1e-9 for d in devueltos)]


def _parse(texto: str, n: int) -> list[str | None]:
    m = re.search(r"\{.*\}", texto, re.DOTALL)
    try:
        datos = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return [None] * n
    out: list[str | None] = [None] * n
    for k, e in enumerate(datos.get("veredictos") or []):
        if not isinstance(e, dict):
            continue
        i = e.get("i", k + 1)
        v = str(e.get("v", "")).strip().lower()
        try:
            i = int(i)
        except (TypeError, ValueError):
            continue
        if 1 <= i <= n and v in VEREDICTOS:
            out[i - 1] = v
    return out


def reintentar(fn, intentos: int = 4, espera_s: float = 20):
    """Calls ``fn`` again when the connection to the model server drops (timeouts, resets); other errors propagate."""
    for k in range(intentos):
        try:
            return fn()
        except httpx.TransportError:
            if k == intentos - 1:
                raise
            time.sleep(espera_s * (k + 1))


class Juez:
    """A local model on Ollama's native chat endpoint, used to label sentences: temperature 0, JSON output, an
    explicit context window (the server default of 4096 tokens can cut the evidence), and reasoning off for the models
    that support switching it."""

    def __init__(self, base_url: str, model: str, num_ctx: int = 8192, timeout_s: float = 900):
        self.base = base_url.rstrip("/").removesuffix("/v1")
        self.model, self.num_ctx = model, num_ctx
        self.http = httpx.Client(timeout=timeout_s)
        self.think: bool | None = False
        self.name = f"local:{model}"

    def chat(self, system: str, prompt: str) -> str:
        cuerpo = {"model": self.model, "stream": False, "format": "json",
                  "options": {"temperature": 0, "num_ctx": self.num_ctx, "seed": 20261126},
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
        if self.think is not None:
            cuerpo["think"] = self.think
        r = reintentar(lambda: self.http.post(f"{self.base}/api/chat", json=cuerpo))
        if r.status_code == 400 and self.think is not None and "think" in r.text.lower():
            self.think = None            # the model has no switchable reasoning
            return self.chat(system, prompt)
        r.raise_for_status()
        return r.json()["message"]["content"]


def juzgar(juez: Juez, frases: list[str], evidencia: list[str], intentos: int = 2) -> list[str | None]:
    """One label per sentence; a sentence left without a valid label after the retries stays ``None``."""
    if not frases:
        return []
    prompt = ("Oraciones de la respuesta:\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(frases, 1))
              + "\n\nEvidencia citada:\n" + "\n\n".join(evidencia))
    out: list[str | None] = [None] * len(frases)
    for _ in range(intentos):
        nuevo = _parse(juez.chat(JUEZ_ORACIONES, prompt), len(frases))
        out = [a or b for a, b in zip(out, nuevo)]
        if all(out):
            break
        time.sleep(0.5)
    return out
