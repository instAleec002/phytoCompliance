"""Scoring of the answers to the structured suite S1 (stage 5), as fixed in the plan before measuring (24/11/2026).

An answer is exact when it gives the expected value with its unit: limits in mg/kg, the pre-harvest interval in days,
the mode-of-action group with its scheme; a yes/no question must start with the right «Sí» or «No»; a comparison must
give both values and name the stricter market. With tools, a value in the answer that no tool returned counts as
invented."""
from __future__ import annotations

import re
import unicodedata

from assistant.orchestration.verificacion import valores_sin_respaldo

NUM = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)(?![\w])")
MERCADOS = {"EU": ("union europea", "ue", "europa"), "US": ("estados unidos", "eeuu", "ee uu", "usa")}


def _n(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return " ".join(t.replace("/", " / ").split())


def numeros(text: str) -> list[float]:
    return [float(x.replace(",", ".")) for x in NUM.findall(text or "")]


def _tiene(text: str, valor) -> bool:
    return valor is not None and any(abs(x - float(valor)) < 1e-9 for x in numeros(text))


def exacta(item: dict, texto: str) -> bool:
    t, e, n = item["tipo"], item["esperado"], _n(texto)
    if t.startswith("lmr_"):
        return _tiene(texto, e["valor_mg_kg"]) and "mg / kg" in n
    if t == "comparacion":
        estricto = e["mercado_mas_estricto"]
        frases = [f for f in re.split(r"[.;\n]", n) if "estrict" in f]
        nombra = any(any(re.search(rf"\b{re.escape(a)}\b", f) for a in MERCADOS[estricto]) for f in frases)
        return _tiene(texto, e["ue_mg_kg"]) and _tiene(texto, e["eeuu_mg_kg"]) and nombra
    if t == "registro":
        return n.startswith("si") if e["registrado"] else n.startswith("no")
    if t == "carencia":
        return _tiene(texto, e["dias"]) and "dia" in n
    if t == "modo_accion":
        return (re.search(rf"(?<![\w]){re.escape(_n(e['grupo']))}(?![\w])", n) is not None
                and _n(e["esquema"]) in n)
    raise ValueError(f"tipo desconocido: {t}")


def inventados(texto: str, llamadas: list[dict]) -> list[float]:
    """Values given with a unit (mg/kg or días) that no tool result contains (the check the agent's output guard
    runs, in assistant.orchestration.verificacion)."""
    return valores_sin_respaldo(texto, llamadas)
